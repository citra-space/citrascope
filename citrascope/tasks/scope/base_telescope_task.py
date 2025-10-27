import os
import time
from abc import ABC, abstractmethod

from dateutil import parser as dtparser
from skyfield.api import EarthSatellite, load, wgs84


class AbstractBaseTelescopeTask(ABC):
    def __init__(self, api_client, hardware_adapter, logger, telescope_record, ground_station_record, task):
        self.api_client = api_client
        self.hardware_adapter = hardware_adapter
        self.logger = logger
        self.telescope_record = telescope_record
        self.ground_station_record = ground_station_record
        self.task = task

    def fetch_satellite_and_elset(self):
        satellite_data = self.api_client.get_satellite(self.task.satelliteId)
        if not satellite_data:
            self.logger.error(f"Could not fetch satellite data for {self.task.satelliteId}")
            return None, None
        elsets = satellite_data.get("elsets", [])
        if not elsets:
            self.logger.error(f"No elsets found for satellite {self.task.satelliteId}")
            return None, None
        most_recent_elset = max(
            elsets,
            key=lambda e: (
                dtparser.isoparse(e["creationEpoch"])
                if e.get("creationEpoch")
                else dtparser.isoparse("1970-01-01T00:00:00Z")
            ),
        )
        return satellite_data, most_recent_elset

    def get_target_radec(self, satellite_data, most_recent_elset):
        ts = load.timescale()
        ground_station = wgs84.latlon(
            self.ground_station_record["latitude"],
            self.ground_station_record["longitude"],
            elevation_m=self.ground_station_record["altitude"],
        )
        satellite = EarthSatellite(most_recent_elset["tle"][0], most_recent_elset["tle"][1], satellite_data["name"], ts)
        difference = satellite - ground_station
        topocentric = difference.at(ts.now())
        target_ra, target_dec, _ = topocentric.radec()
        return target_ra, target_dec, satellite_data["name"]

    def upload_image_and_mark_complete(self, filepath):
        upload_result = self.api_client.upload_image(self.task.id, self.telescope_record["id"], filepath)
        if upload_result:
            self.logger.info(f"Successfully uploaded image for task {self.task.id}")
        else:
            self.logger.error(f"Failed to upload image for task {self.task.id}")
        try:
            os.remove(filepath)
            self.logger.info(f"Deleted local image file {filepath} after upload.")
        except Exception as e:
            self.logger.error(f"Failed to delete local image file {filepath}: {e}")
        marked_complete = self.api_client.mark_task_complete(self.task.id)
        if not marked_complete:
            task_check = self.api_client.get_telescope_tasks(self.telescope_record["id"])
            for t in task_check:
                if t["id"] == self.task.id and t.get("status") == "Succeeded":
                    self.logger.info(f"Task {self.task.id} is already marked complete.")
                    return True
            self.logger.error(f"Failed to mark task {self.task.id} as complete.")
            return False
        self.logger.info(f"Marked task {self.task.id} as complete.")
        return True

    @abstractmethod
    def execute(self):
        pass
