import time
from typing import Optional

from citrascope.api.citra_api_client import AbstractCitraApiClient, CitraApiClient
from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter
from citrascope.hardware.indi_adapter import IndiAdapter
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
        self.hardware_adapter = hardware_adapter or IndiAdapter(
            CITRASCOPE_LOGGER, self.settings.indi_server_url, int(self.settings.indi_server_port)
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
        CITRASCOPE_LOGGER.info(f"Connecting to hardware server with {type(self.hardware_adapter).__name__}...")
        self.hardware_adapter.connect()  # TODO: change this to not have url, port
        time.sleep(1)
        CITRASCOPE_LOGGER.info("List of hardware devices")
        device_list = self.hardware_adapter.list_devices() or []

        # check for telescope
        if not self.settings.indi_telescope_name in device_list:
            CITRASCOPE_LOGGER.error(
                f"Aborting: could not find configured telescope ({self.settings.indi_telescope_name}) on hardware server."
            )
            return
        self.hardware_adapter.select_telescope(self.settings.indi_telescope_name)
        self.hardware_adapter.scope_slew_rate_degrees_per_second = citra_telescope_record["maxSlewRate"]
        CITRASCOPE_LOGGER.info(f"Found configured Telescope ({self.settings.indi_telescope_name}) on hardware server!")

        # check for camera
        if not self.settings.indi_camera_name in device_list:
            CITRASCOPE_LOGGER.error(
                f"Aborting: could not find configured camera ({self.settings.indi_camera_name}) on hardware server."
            )
            return
        self.hardware_adapter.select_camera(self.settings.indi_camera_name)
        CITRASCOPE_LOGGER.info(f"Found configured Camera ({self.settings.indi_camera_name}) on hardware server!")

        task_manager = TaskManager(
            self.api_client, citra_telescope_record, ground_station, CITRASCOPE_LOGGER, self.hardware_adapter
        )
        task_manager.start()

        CITRASCOPE_LOGGER.info("Starting telescope task daemon... (press Ctrl+C to exit)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            CITRASCOPE_LOGGER.info("Shutting down daemon.")
            task_manager.stop()
