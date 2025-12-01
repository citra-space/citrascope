import time
from typing import Optional

from citrascope.api.citra_api_client import AbstractCitraApiClient, CitraApiClient
from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter
from citrascope.hardware.nina_adv_http_adapter import NinaAdvancedHttpAdapter
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings._citrascope_settings import CitraScopeSettings
from citrascope.tasks.runner import TaskManager


class CitraScopeDaemon:
    def __init__(
        self,
        settings: CitraScopeSettings,
        api_client: Optional[AbstractCitraApiClient] = None,
        hardware_adapter: Optional[AbstractAstroHardwareAdapter] = None,
    ):
        self.settings = settings
        CITRASCOPE_LOGGER.setLevel(self.settings.log_level)
        self.api_client = api_client or CitraApiClient(
            self.settings.host,
            self.settings.personal_access_token,
            self.settings.use_ssl,
            CITRASCOPE_LOGGER,
        )
        self.hardware_adapter = hardware_adapter or self._create_hardware_adapter()

    def _create_hardware_adapter(self) -> AbstractAstroHardwareAdapter:
        """Factory method to create the appropriate hardware adapter based on settings."""
        if self.settings.hardware_adapter == "indi":
            try:
                from citrascope.hardware.indi_adapter import IndiAdapter

                return IndiAdapter(
                    CITRASCOPE_LOGGER,
                    self.settings.indi_server_url,
                    int(self.settings.indi_server_port),
                    self.settings.indi_telescope_name,
                    self.settings.indi_camera_name,
                )
            except ImportError as e:
                CITRASCOPE_LOGGER.error(
                    f"INDI adapter requested but dependencies not available. "
                    f"Install with: pip install citrascope[indi]. Error: {e}"
                )
                raise RuntimeError(
                    f"INDI adapter requires additional dependencies. " f"Install with: pip install citrascope[indi]"
                ) from e
        elif self.settings.hardware_adapter == "nina":
            return NinaAdvancedHttpAdapter(
                CITRASCOPE_LOGGER,
                self.settings.nina_url_prefix,
                self.settings.nina_scp_command_template,
                bypass_autofocus=self.settings.bypass_autofocus,
            )
        else:
            raise ValueError(
                f"Unknown hardware adapter type: {self.settings.hardware_adapter}. "
                f"Valid options are: 'indi', 'nina'"
            )

    def run(self):
        CITRASCOPE_LOGGER.info(f"CitraAPISettings host is {self.settings.host}")
        CITRASCOPE_LOGGER.info(f"CitraAPISettings telescope_id is {self.settings.telescope_id}")

        # check api for valid key, telescope and ground station
        if not self.api_client.does_api_server_accept_key():
            CITRASCOPE_LOGGER.error("Aborting: could not authenticate with Citra API.")
            return

        citra_telescope_record = self.api_client.get_telescope(self.settings.telescope_id)
        if not citra_telescope_record:
            CITRASCOPE_LOGGER.error("Aborting: telescope_id is not valid on the server.")
            return

        ground_station = self.api_client.get_ground_station(citra_telescope_record["groundStationId"])
        if not ground_station:
            CITRASCOPE_LOGGER.error("Aborting: could not get ground station info from the server.")
            return

        # connect to hardware server
        CITRASCOPE_LOGGER.info(f"Connecting to hardware with {type(self.hardware_adapter).__name__}...")
        if not self.hardware_adapter.connect():
            CITRASCOPE_LOGGER.error("Aborting: failed to connect to hardware.")
            return

        self.hardware_adapter.scope_slew_rate_degrees_per_second = citra_telescope_record["maxSlewRate"]
        CITRASCOPE_LOGGER.info(
            f"Hardware connected. Slew rate: {self.hardware_adapter.scope_slew_rate_degrees_per_second} deg/sec"
        )

        task_manager = TaskManager(
            self.api_client,
            citra_telescope_record,
            ground_station,
            CITRASCOPE_LOGGER,
            self.hardware_adapter,
            self.settings.keep_images,
        )
        task_manager.start()

        CITRASCOPE_LOGGER.info("Starting telescope task daemon... (press Ctrl+C to exit)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            CITRASCOPE_LOGGER.info("Shutting down daemon.")
            task_manager.stop()
