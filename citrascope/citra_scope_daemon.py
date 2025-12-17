import time
from typing import Optional

from citrascope.api.citra_api_client import AbstractCitraApiClient, CitraApiClient
from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter
from citrascope.hardware.adapter_registry import get_adapter_class
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.logging._citrascope_logger import setup_file_logging
from citrascope.settings.citrascope_settings import CitraScopeSettings
from citrascope.tasks.runner import TaskManager
from citrascope.web.server import CitraScopeWebServer


class CitraScopeDaemon:
    def __init__(
        self,
        settings: CitraScopeSettings,
        api_client: Optional[AbstractCitraApiClient] = None,
        hardware_adapter: Optional[AbstractAstroHardwareAdapter] = None,
    ):
        self.settings = settings
        CITRASCOPE_LOGGER.setLevel(self.settings.log_level)

        # Setup file logging if enabled
        if self.settings.file_logging_enabled:
            self.settings.config_manager.ensure_log_directory()
            log_path = self.settings.config_manager.get_current_log_path()
            setup_file_logging(log_path, backup_count=self.settings.log_retention_days)
            CITRASCOPE_LOGGER.info(f"Logging to file: {log_path}")

        self.api_client = api_client
        self.hardware_adapter = hardware_adapter
        self.web_server = None
        self.task_manager = None
        self.ground_station = None
        self.telescope_record = None
        self.configuration_error: Optional[str] = None

        # Create web server instance (always enabled)
        self.web_server = CitraScopeWebServer(daemon=self, host="0.0.0.0", port=self.settings.web_port)

    def _create_hardware_adapter(self) -> AbstractAstroHardwareAdapter:
        """Factory method to create the appropriate hardware adapter based on settings."""
        try:
            adapter_class = get_adapter_class(self.settings.hardware_adapter)
            # Ensure images directory exists and pass it to the adapter
            self.settings.ensure_images_directory()
            images_dir = self.settings.get_images_dir()
            return adapter_class(logger=CITRASCOPE_LOGGER, images_dir=images_dir, **self.settings.adapter_settings)
        except ImportError as e:
            CITRASCOPE_LOGGER.error(
                f"{self.settings.hardware_adapter} adapter requested but dependencies not available. " f"Error: {e}"
            )
            raise RuntimeError(
                f"{self.settings.hardware_adapter} adapter requires additional dependencies. "
                f"Check documentation for installation instructions."
            ) from e

    def _initialize_components(self, reload_settings: bool = False) -> tuple[bool, Optional[str]]:
        """Initialize or reinitialize all components.

        Args:
            reload_settings: If True, reload settings from disk before initializing

        Returns:
            Tuple of (success, error_message)
        """
        try:
            if reload_settings:
                CITRASCOPE_LOGGER.info("Reloading configuration...")
                # Reload settings from file (preserving web_port)
                new_settings = CitraScopeSettings(web_port=self.settings.web_port)
                self.settings = new_settings
                CITRASCOPE_LOGGER.setLevel(self.settings.log_level)

                # Ensure web log handler is still attached after logger changes
                if self.web_server:
                    self.web_server.ensure_log_handler()

                # Re-setup file logging if enabled
                if self.settings.file_logging_enabled:
                    self.settings.config_manager.ensure_log_directory()
                    log_path = self.settings.config_manager.get_current_log_path()
                    setup_file_logging(log_path, backup_count=self.settings.log_retention_days)

            # Cleanup existing resources
            if self.task_manager:
                CITRASCOPE_LOGGER.info("Stopping existing task manager...")
                self.task_manager.stop()
                self.task_manager = None

            if self.hardware_adapter:
                try:
                    self.hardware_adapter.disconnect()
                except Exception as e:
                    CITRASCOPE_LOGGER.warning(f"Error disconnecting hardware: {e}")
                self.hardware_adapter = None

            # Check if configuration is complete
            if not self.settings.is_configured():
                error_msg = "Configuration incomplete. Please set access token, telescope ID, and hardware adapter."
                CITRASCOPE_LOGGER.warning(error_msg)
                self.configuration_error = error_msg
                return False, error_msg

            # Initialize API client
            self.api_client = CitraApiClient(
                self.settings.host,
                self.settings.personal_access_token,
                self.settings.use_ssl,
                CITRASCOPE_LOGGER,
            )

            # Initialize hardware adapter
            self.hardware_adapter = self._create_hardware_adapter()

            # Initialize telescope
            success, error = self._initialize_telescope()

            if success:
                self.configuration_error = None
                CITRASCOPE_LOGGER.info("Components initialized successfully!")
                return True, None
            else:
                self.configuration_error = error
                return False, error

        except Exception as e:
            error_msg = f"Failed to initialize components: {str(e)}"
            CITRASCOPE_LOGGER.error(error_msg, exc_info=True)
            self.configuration_error = error_msg
            return False, error_msg

    def reload_configuration(self) -> tuple[bool, Optional[str]]:
        """Reload configuration from file and reinitialize all components."""
        return self._initialize_components(reload_settings=True)

    def _initialize_telescope(self) -> tuple[bool, Optional[str]]:
        """Initialize telescope connection and task manager.

        Returns:
            Tuple of (success, error_message)
        """
        try:
            CITRASCOPE_LOGGER.info(f"CitraAPISettings host is {self.settings.host}")
            CITRASCOPE_LOGGER.info(f"CitraAPISettings telescope_id is {self.settings.telescope_id}")

            # check api for valid key, telescope and ground station
            if not self.api_client.does_api_server_accept_key():
                error_msg = "Could not authenticate with Citra API. Check your access token."
                CITRASCOPE_LOGGER.error(error_msg)
                return False, error_msg

            citra_telescope_record = self.api_client.get_telescope(self.settings.telescope_id)
            if not citra_telescope_record:
                error_msg = f"Telescope ID '{self.settings.telescope_id}' is not valid on the server."
                CITRASCOPE_LOGGER.error(error_msg)
                return False, error_msg
            self.telescope_record = citra_telescope_record

            ground_station = self.api_client.get_ground_station(citra_telescope_record["groundStationId"])
            if not ground_station:
                error_msg = "Could not get ground station info from the server."
                CITRASCOPE_LOGGER.error(error_msg)
                return False, error_msg
            self.ground_station = ground_station

            # connect to hardware server
            CITRASCOPE_LOGGER.info(f"Connecting to hardware with {type(self.hardware_adapter).__name__}...")
            if not self.hardware_adapter.connect():
                error_msg = f"Failed to connect to hardware adapter: {type(self.hardware_adapter).__name__}"
                CITRASCOPE_LOGGER.error(error_msg)
                return False, error_msg

            self.hardware_adapter.scope_slew_rate_degrees_per_second = citra_telescope_record["maxSlewRate"]
            CITRASCOPE_LOGGER.info(
                f"Hardware connected. Slew rate: {self.hardware_adapter.scope_slew_rate_degrees_per_second} deg/sec"
            )

            self.task_manager = TaskManager(
                self.api_client,
                citra_telescope_record,
                ground_station,
                CITRASCOPE_LOGGER,
                self.hardware_adapter,
                self.settings.keep_images,
                self.settings,
            )
            self.task_manager.start()

            CITRASCOPE_LOGGER.info("Telescope initialized successfully!")
            return True, None

        except Exception as e:
            error_msg = f"Error initializing telescope: {str(e)}"
            CITRASCOPE_LOGGER.error(error_msg, exc_info=True)
            return False, error_msg

    def run(self):
        # Start web server FIRST, so users can monitor/configure
        # The web interface will remain available even if configuration is incomplete
        self.web_server.start()
        CITRASCOPE_LOGGER.info(f"Web interface available at http://{self.web_server.host}:{self.web_server.port}")

        try:
            # Try to initialize components
            success, error = self._initialize_components()
            if not success:
                CITRASCOPE_LOGGER.warning(
                    f"Could not start telescope operations: {error}. "
                    f"Configure via web interface at http://{self.web_server.host}:{self.web_server.port}"
                )

            CITRASCOPE_LOGGER.info("Starting telescope task daemon... (press Ctrl+C to exit)")
            self._keep_running()
        finally:
            self._shutdown()

    def _keep_running(self):
        """Keep the daemon running until interrupted."""
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            CITRASCOPE_LOGGER.info("Shutting down daemon.")

    def _shutdown(self):
        """Clean up resources on shutdown."""
        if self.task_manager:
            self.task_manager.stop()
        if self.web_server:
            CITRASCOPE_LOGGER.info("Stopping web server...")
            if self.web_server.web_log_handler:
                CITRASCOPE_LOGGER.removeHandler(self.web_server.web_log_handler)
