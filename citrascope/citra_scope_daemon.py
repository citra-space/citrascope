import time
from typing import Optional

from citrascope.api.client import AbstractCitraApiClient, CitraApiClient
from citrascope.indi.CitraIndiClient import CitraIndiClient
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings._citrascope_settings import CitraScopeSettings
from citrascope.tasks.runner import TaskManager


class CitraScopeDaemon:
    def __init__(self, dev: bool, log_level: str, api_client: Optional[AbstractCitraApiClient] = None):
        self.dev = dev
        self.log_level = log_level
        CITRASCOPE_LOGGER.setLevel(log_level)
        self.settings = CitraScopeSettings(dev=dev)
        self.api_client = api_client or CitraApiClient(
            self.settings.host,
            self.settings.personal_access_token,
            self.settings.use_ssl,
            CITRASCOPE_LOGGER,
        )

    def run(self):
        CITRASCOPE_LOGGER.info(f"CitraAPISettings host is {self.settings.host}")
        CITRASCOPE_LOGGER.info(f"CitraAPISettings telescope_id is {self.settings.telescope_id}")

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

        CITRASCOPE_LOGGER.info(
            f"Connecting to INDI server at {self.settings.indi_server_url}: {self.settings.indi_server_port}"
        )
        indi_client = CitraIndiClient(CITRASCOPE_LOGGER)
        indi_client.setServer(self.settings.indi_server_url, int(self.settings.indi_server_port))
        print("Connecting and waiting 1 sec")
        if not indi_client.connectServer():
            print(f"No INDI server running on {indi_client.getHost()}:{indi_client.getPort()}")
            return

        time.sleep(1)

        CITRASCOPE_LOGGER.info("List of INDI devices")
        deviceList = indi_client.getDevices()
        for device in deviceList:
            CITRASCOPE_LOGGER.info(f"   > {device.getDeviceName()}")
            if device.getDeviceName() == self.settings.indi_telescope_name:
                indi_client.our_scope = device
                CITRASCOPE_LOGGER.info("Found configured Telescope on INDI server!")

        task_manager = TaskManager(
            self.api_client, citra_telescope_record, ground_station, CITRASCOPE_LOGGER, indi_client
        )
        task_manager.start()

        CITRASCOPE_LOGGER.info("Starting telescope task daemon... (press Ctrl+C to exit)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            CITRASCOPE_LOGGER.info("Shutting down daemon.")
            task_manager.stop()
