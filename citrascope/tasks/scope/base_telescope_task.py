import os
import time
from abc import ABC, abstractmethod

from dateutil import parser as dtparser
from skyfield.api import Angle, EarthSatellite, load, wgs84

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter


class AbstractBaseTelescopeTask(ABC):
    def __init__(
        self,
        api_client,
        hardware_adapter: AbstractAstroHardwareAdapter,
        logger,
        telescope_record,
        ground_station_record,
        task,
    ):
        self.api_client = api_client
        self.hardware_adapter: AbstractAstroHardwareAdapter = hardware_adapter
        self.logger = logger
        self.telescope_record = telescope_record
        self.ground_station_record = ground_station_record
        self.task = task

    def fetch_satellite(self) -> dict | None:
        satellite_data = self.api_client.get_satellite(self.task.satelliteId)
        if not satellite_data:
            self.logger.error(f"Could not fetch satellite data for {self.task.satelliteId}")
            return None
        elsets = satellite_data.get("elsets", [])
        if not elsets:
            self.logger.error(f"No elsets found for satellite {self.task.satelliteId}")
            return None
        satellite_data["most_recent_elset"] = self._get_most_recent_elset(satellite_data)
        return satellite_data

    def _get_most_recent_elset(self, satellite_data) -> dict | None:
        if "most_recent_elset" in satellite_data:
            return satellite_data["most_recent_elset"]

        elsets = satellite_data.get("elsets", [])
        if not elsets:
            self.logger.error(f"No elsets found for satellite {self.task.satelliteId}")
            return None
        most_recent_elset = max(
            elsets,
            key=lambda e: (
                dtparser.isoparse(e["creationEpoch"])
                if e.get("creationEpoch")
                else dtparser.isoparse("1970-01-01T00:00:00Z")
            ),
        )
        return most_recent_elset

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

    def _get_skyfield_ground_station_and_satellite(self, satellite_data):
        """
        Returns (ground_station, satellite, ts) Skyfield objects for the given satellite and elset.
        """
        ts = load.timescale()
        most_recent_elset = self._get_most_recent_elset(satellite_data)
        if most_recent_elset is None:
            raise ValueError("No valid elset available for satellite.")

        ground_station = wgs84.latlon(
            self.ground_station_record["latitude"],
            self.ground_station_record["longitude"],
            elevation_m=self.ground_station_record["altitude"],
        )
        satellite = EarthSatellite(most_recent_elset["tle"][0], most_recent_elset["tle"][1], satellite_data["name"], ts)
        return ground_station, satellite, ts

    def get_target_radec(self, satellite_data):
        ground_station, satellite, ts = self._get_skyfield_ground_station_and_satellite(satellite_data)
        difference = satellite - ground_station
        topocentric = difference.at(ts.now())
        target_ra, target_dec, _ = topocentric.radec()
        return target_ra, target_dec

    def get_predicted_slew_time_and_sat_radec(
        self, satellite_data, margin_time_sec: float = 5.0
    ) -> tuple[float, tuple[Angle, Angle]]:
        """
        Estimate the slew time (in seconds) required to move from the current telescope position
        to the predicted satellite position after the slew time.
        """

        # Get current directions
        current_scope_ra, current_scope_dec = self.hardware_adapter.get_telescope_direction()
        current_target_ra, current_target_dec = self.get_target_radec(satellite_data)

        # Compute angular distance in degrees between current scope position and target position
        ra_diff_deg = abs((current_target_ra.degrees - current_scope_ra))  # Convert hours to degrees
        dec_diff_deg = abs(current_target_dec.degrees - current_scope_dec)
        angular_distance_deg = (ra_diff_deg**2 + dec_diff_deg**2) ** 0.5

        # Estimate slew time based on hardware's measured slew rate
        if self.hardware_adapter.scope_slew_rate_degrees_per_second <= 0.0:
            estimated_slew_time_sec = 60.0  # Default to 60 seconds if unknown
            self.logger.warning("Scope slew rate unknown, defaulting estimated slew time to 60 seconds.")
        else:
            estimated_slew_time_sec = angular_distance_deg / self.hardware_adapter.scope_slew_rate_degrees_per_second

        # calculate future position after estimated slew time + margin
        ground_station, satellite, ts = self._get_skyfield_ground_station_and_satellite(satellite_data)
        future_time = ts.now() + (estimated_slew_time_sec + margin_time_sec) / 86400.0  # convert seconds to days
        difference = satellite - ground_station
        topocentric = difference.at(future_time)
        target_ra, target_dec, _ = topocentric.radec()

        self.logger.info(
            f"Estimated slew time: {estimated_slew_time_sec:.1f} sec for {angular_distance_deg:.2f} deg move"
        )
        return estimated_slew_time_sec, (target_ra, target_dec)
