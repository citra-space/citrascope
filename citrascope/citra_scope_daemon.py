import time
from typing import Optional

from citrascope.api.citra_api_client import AbstractCitraApiClient, CitraApiClient
from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter
from citrascope.hardware.adapter_registry import get_adapter_class
from citrascope.hardware.filter_sync import sync_filters_to_backend
from citrascope.location import LocationService
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.logging._citrascope_logger import setup_file_logging
from citrascope.settings.citrascope_settings import CitraScopeSettings
from citrascope.tasks.runner import TaskManager
from citrascope.time.time_health import TimeHealth
from citrascope.time.time_monitor import TimeMonitor
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
        self.time_monitor = None
        self.location_service = None
        self.ground_station = None
        self.telescope_record = None
        self.configuration_error: Optional[str] = None

        # Initialize processor registry
        from citrascope.processors.processor_registry import ProcessorRegistry

        self.processor_registry = ProcessorRegistry(settings=self.settings, logger=CITRASCOPE_LOGGER)

        # Initialize background queues for pipeline
        import threading

        from citrascope.tasks.processing_queue import ProcessingQueue
        from citrascope.tasks.upload_queue import UploadQueue

        self.processing_queue = ProcessingQueue(
            num_workers=1, logger=CITRASCOPE_LOGGER  # One processing task at a time
        )
        self.upload_queue = UploadQueue(num_workers=1, logger=CITRASCOPE_LOGGER)  # One upload at a time

        # Start background workers
        CITRASCOPE_LOGGER.info("Starting background processing workers...")
        self.processing_queue.start()
        self.upload_queue.start()

        # Simple stage tracking (thread-safe)
        self._stage_lock = threading.Lock()
        self.shooting_tasks = {}  # task_id -> start_time (float)
        self.processing_tasks = {}  # task_id -> start_time (float)
        self.uploading_tasks = {}  # task_id -> start_time (float)

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

            if self.time_monitor:
                self.time_monitor.stop()
                self.time_monitor = None

            if self.location_service:
                self.location_service.stop()
                self.location_service = None

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

            # Check for missing dependencies (non-fatal, just warn)
            if hasattr(self.hardware_adapter, "get_missing_dependencies"):
                missing_deps = self.hardware_adapter.get_missing_dependencies()
                if missing_deps:
                    for dep in missing_deps:
                        CITRASCOPE_LOGGER.warning(
                            f"{dep['device_type']} '{dep['device_name']}' missing dependencies: {dep['missing_packages']}. "
                            f"Install with: {dep['install_cmd']}"
                        )

            # Initialize location service (manages GPS internally)
            self.location_service = LocationService(
                api_client=self.api_client,
                settings=self.settings,
            )

            # Initialize time monitor with GPS reference from location service
            self.time_monitor = TimeMonitor(
                check_interval_minutes=self.settings.time_check_interval_minutes,
                pause_threshold_ms=self.settings.time_offset_pause_ms,
                pause_callback=self._on_time_drift_pause,
                gps_monitor=self.location_service.gps_monitor if self.location_service else None,
            )
            self.time_monitor.start()
            CITRASCOPE_LOGGER.info("Time synchronization monitoring started")

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

            # Update location service with ground station reference
            if self.location_service:
                self.location_service.set_ground_station(self.ground_station)

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

            # Save filter configuration if adapter supports it
            self._save_filter_config()
            # Sync discovered filters to backend on startup
            self._sync_filters_to_backend()

            self.task_manager = TaskManager(
                self.api_client,
                CITRASCOPE_LOGGER,
                self.hardware_adapter,
                self,
            )
            self.task_manager.start()

            CITRASCOPE_LOGGER.info("Telescope initialized successfully!")
            return True, None

        except Exception as e:
            error_msg = f"Error initializing telescope: {str(e)}"
            CITRASCOPE_LOGGER.error(error_msg, exc_info=True)
            return False, error_msg

    def _save_filter_config(self):
        """Save filter configuration from adapter to settings if supported.

        This method is called:
        - After hardware initialization to save discovered filters
        - After autofocus to save updated focus positions
        - After manual filter focus updates via web API

        Note: This only saves locally. Call _sync_filters_to_backend() separately
        when enabled filters change to update the backend.

        Thread safety: This modifies self.settings and writes to disk.
        Should be called from main daemon thread or properly synchronized.
        """
        if not self.hardware_adapter or not self.hardware_adapter.supports_filter_management():
            return

        try:
            filter_config = self.hardware_adapter.get_filter_config()
            if filter_config:
                self.settings.adapter_settings["filters"] = filter_config
                self.settings.save()
                CITRASCOPE_LOGGER.info(f"Saved filter configuration with {len(filter_config)} filters")
        except Exception as e:
            CITRASCOPE_LOGGER.warning(f"Failed to save filter configuration: {e}")

    def _sync_filters_to_backend(self):
        """Sync enabled filters to backend API.

        Extracts enabled filter names from hardware adapter, expands them via
        the filter library API, then updates the telescope's spectral_config.
        Logs warnings on failure without blocking daemon operations.
        """
        if not self.hardware_adapter or not self.api_client or not self.telescope_record:
            return

        try:
            filter_config = self.hardware_adapter.get_filter_config()
            sync_filters_to_backend(self.api_client, self.telescope_record["id"], filter_config, CITRASCOPE_LOGGER)
        except Exception as e:
            CITRASCOPE_LOGGER.warning(f"Failed to sync filters to backend: {e}", exc_info=True)

    def trigger_autofocus(self) -> tuple[bool, Optional[str]]:
        """Request autofocus to run at next safe point between tasks.

        Returns:
            Tuple of (success, error_message)
        """
        if not self.hardware_adapter:
            return False, "No hardware adapter initialized"

        if not self.hardware_adapter.supports_filter_management():
            return False, "Hardware adapter does not support filter management"

        if not self.task_manager:
            return False, "Task manager not initialized"

        # Request autofocus - will run between tasks
        self.task_manager.request_autofocus()
        return True, None

    def cancel_autofocus(self) -> bool:
        """Cancel pending autofocus request if queued.

        Returns:
            bool: True if autofocus was cancelled, False if nothing to cancel.
        """
        if not self.task_manager:
            return False
        return self.task_manager.cancel_autofocus()

    def is_autofocus_requested(self) -> bool:
        """Check if autofocus is currently queued.

        Returns:
            bool: True if autofocus is queued, False otherwise.
        """
        if not self.task_manager:
            return False
        return self.task_manager.is_autofocus_requested()

    def _on_time_drift_pause(self, health: TimeHealth) -> None:
        """
        Callback invoked when time drift exceeds pause threshold.

        Automatically pauses task processing to prevent observations with
        inaccurate timestamps. User must manually resume after fixing time sync.

        Args:
            health: Current time health status
        """
        if not self.task_manager:
            return

        CITRASCOPE_LOGGER.critical(
            f"Time drift exceeded threshold: {health.offset_ms:+.1f}ms. "
            "Pausing task processing to prevent inaccurate observations."
        )

        # Pause task processing
        self.task_manager.pause()
        CITRASCOPE_LOGGER.warning(
            "Task processing paused due to time sync issues. "
            "Fix NTP configuration and manually resume via web interface."
        )

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

    def update_task_stage(self, task_id: str, stage: str):
        """Move task to specified stage. Stage is 'shooting', 'processing', or 'uploading'."""
        with self._stage_lock:
            # Remove from all stages first
            self.shooting_tasks.pop(task_id, None)
            self.processing_tasks.pop(task_id, None)
            self.uploading_tasks.pop(task_id, None)

            # Add to new stage
            if stage == "shooting":
                self.shooting_tasks[task_id] = time.time()
            elif stage == "processing":
                self.processing_tasks[task_id] = time.time()
            elif stage == "uploading":
                self.uploading_tasks[task_id] = time.time()

    def remove_task_from_stages(self, task_id: str):
        """Remove task from all stages (when complete)."""
        with self._stage_lock:
            self.shooting_tasks.pop(task_id, None)
            self.processing_tasks.pop(task_id, None)
            self.uploading_tasks.pop(task_id, None)

    def get_tasks_by_stage(self) -> dict:
        """Get current tasks in each stage, enriched with task details from task manager."""
        with self._stage_lock:
            now = time.time()

            def enrich_task(task_id: str, start_time: float) -> dict:
                """Look up task details and create enriched dict."""
                result = {"task_id": task_id, "elapsed": now - start_time}
                # Look up task from task manager if available
                if self.task_manager:
                    task = self.task_manager.get_task_by_id(task_id)
                    if task:
                        result["target_name"] = task.satelliteName
                return result

            return {
                "shooting": [enrich_task(tid, start) for tid, start in self.shooting_tasks.items()],
                "processing": [enrich_task(tid, start) for tid, start in self.processing_tasks.items()],
                "uploading": [enrich_task(tid, start) for tid, start in self.uploading_tasks.items()],
            }

    def _shutdown(self):
        """Clean up resources on shutdown."""
        # Stop background workers
        if hasattr(self, "processing_queue"):
            self.processing_queue.stop()
        if hasattr(self, "upload_queue"):
            self.upload_queue.stop()

        if self.task_manager:
            self.task_manager.stop()
        if self.time_monitor:
            self.time_monitor.stop()
        if self.web_server:
            CITRASCOPE_LOGGER.info("Stopping web server...")
            if self.web_server.web_log_handler:
                CITRASCOPE_LOGGER.removeHandler(self.web_server.web_log_handler)
