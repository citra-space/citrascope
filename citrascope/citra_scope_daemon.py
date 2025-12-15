import time
from typing import Optional

from citrascope.api.citra_api_client import AbstractCitraApiClient, CitraApiClient
from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter
from citrascope.hardware.adapter_registry import get_adapter_class
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings._citrascope_settings import CitraScopeSettings
from citrascope.tasks.runner import TaskManager
from citrascope.web.server import CitraScopeWebServer


class CitraScopeDaemon:
    def __init__(
        self,
        settings: CitraScopeSettings,
        api_client: Optional[AbstractCitraApiClient] = None,
        hardware_adapter: Optional[AbstractAstroHardwareAdapter] = None,
        enable_web: bool = True,
        web_host: str = "0.0.0.0",
        web_port: int = 24872,
    ):
        self.settings = settings
        CITRASCOPE_LOGGER.setLevel(self.settings.log_level)
        self.api_client = api_client
        self.hardware_adapter = hardware_adapter
        self.enable_web = enable_web
        self.web_server = None
        self.task_manager = None
        self.ground_station = None
        self.telescope_record = None
        self.configuration_error: Optional[str] = None

        # Create web server instance if enabled (always start web server)
        if self.enable_web:
            self.web_server = CitraScopeWebServer(daemon=self, host=web_host, port=web_port)

    def _create_hardware_adapter(self) -> AbstractAstroHardwareAdapter:
        """Factory method to create the appropriate hardware adapter based on settings."""
        try:
            adapter_class = get_adapter_class(self.settings.hardware_adapter)
            # For NINA adapter, pass bypass_autofocus if it's a NINA adapter
            if self.settings.hardware_adapter == "nina":
                return adapter_class(
                    logger=CITRASCOPE_LOGGER,
                    bypass_autofocus=self.settings.bypass_autofocus,
                    **self.settings.adapter_settings,
                )
            else:
                return adapter_class(logger=CITRASCOPE_LOGGER, **self.settings.adapter_settings)
        except ImportError as e:
            CITRASCOPE_LOGGER.error(
                f"{self.settings.hardware_adapter} adapter requested but dependencies not available. " f"Error: {e}"
            )
            raise RuntimeError(
                f"{self.settings.hardware_adapter} adapter requires additional dependencies. "
                f"Check documentation for installation instructions."
            ) from e

    def reload_configuration(self) -> tuple[bool, Optional[str]]:
        """Reload configuration from file and reinitialize components.

        Returns:
            Tuple of (success, error_message)
        """
        try:
            CITRASCOPE_LOGGER.info("Reloading configuration...")

            # Reload settings from file
            new_settings = CitraScopeSettings(
                dev=("dev.api" in self.settings.host),
                log_level=self.settings.log_level,
                keep_images=self.settings.keep_images,
                bypass_autofocus=self.settings.bypass_autofocus,
            )

            if not new_settings.is_configured():
                error_msg = "Configuration incomplete. Please set access token, telescope ID, and hardware adapter."
                CITRASCOPE_LOGGER.warning(error_msg)
                self.configuration_error = error_msg
                return False, error_msg

            # Stop existing task manager if running
            if self.task_manager:
                CITRASCOPE_LOGGER.info("Stopping existing task manager...")
                self.task_manager.stop()
                self.task_manager = None

            # Disconnect existing hardware if connected
            if self.hardware_adapter:
                try:
                    self.hardware_adapter.disconnect()
                except Exception as e:
                    CITRASCOPE_LOGGER.warning(f"Error disconnecting hardware: {e}")
                self.hardware_adapter = None

            # Update settings
            self.settings = new_settings
            CITRASCOPE_LOGGER.setLevel(self.settings.log_level)

            # Ensure web log handler is still attached after logger changes
            if self.web_server:
                self.web_server.ensure_log_handler()

            # Reinitialize API client
            self.api_client = CitraApiClient(
                self.settings.host,
                self.settings.personal_access_token,
                self.settings.use_ssl,
                CITRASCOPE_LOGGER,
            )

            # Reinitialize hardware adapter
            self.hardware_adapter = self._create_hardware_adapter()

            # Try to initialize everything
            success, error = self._initialize_telescope()

            if success:
                self.configuration_error = None
                CITRASCOPE_LOGGER.info("Configuration reloaded successfully!")
                return True, None
            else:
                self.configuration_error = error
                return False, error

        except Exception as e:
            error_msg = f"Failed to reload configuration: {str(e)}"
            CITRASCOPE_LOGGER.error(error_msg, exc_info=True)
            self.configuration_error = error_msg
            return False, error_msg

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
        # Start web server FIRST if enabled, so users can monitor/configure
        # The web interface will remain available even if configuration is incomplete
        if self.enable_web:
            self.web_server.start()
            CITRASCOPE_LOGGER.info(f"Web interface available at http://{self.web_server.host}:{self.web_server.port}")

        try:
            # Check if configuration is complete
            if not self.settings.is_configured():
                CITRASCOPE_LOGGER.warning(
                    "Configuration incomplete. Please configure via web interface at "
                    f"http://{self.web_server.host}:{self.web_server.port}"
                )
                self.configuration_error = (
                    "Configuration required. Please set access token, telescope ID, and hardware adapter."
                )
                self._keep_running()
                return

            # Initialize API client and hardware adapter if not provided
            if not self.api_client:
                self.api_client = CitraApiClient(
                    self.settings.host,
                    self.settings.personal_access_token,
                    self.settings.use_ssl,
                    CITRASCOPE_LOGGER,
                )

            if not self.hardware_adapter:
                self.hardware_adapter = self._create_hardware_adapter()

            # Try to initialize telescope
            success, error = self._initialize_telescope()
            if not success:
                self.configuration_error = error
                CITRASCOPE_LOGGER.error(f"Failed to initialize: {error}")

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
        if self.enable_web and self.web_server:
            CITRASCOPE_LOGGER.info("Stopping web server...")
            self.web_server.stop()
