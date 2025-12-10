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
        keep_images: bool = False,
    ):
        self.api_client = api_client
        self.hardware_adapter: AbstractAstroHardwareAdapter = hardware_adapter
        self.logger = logger
        self.telescope_record = telescope_record
        self.ground_station_record = ground_station_record
        self.task = task
        self.keep_images = keep_images

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

    def upload_image_and_mark_complete(self, filepath: str | list[str]) -> bool:

        if isinstance(filepath, str):
            filepaths = [filepath]
        else:
            filepaths = filepath

        for filepath in filepaths:
            upload_result = self.api_client.upload_image(self.task.id, self.telescope_record["id"], filepath)
            if upload_result:
                self.logger.info(f"Successfully uploaded image {filepath}")
            else:
                self.logger.error(f"Failed to upload image {filepath}")
                return False

            if not self.keep_images:
                try:
                    os.remove(filepath)
                    self.logger.debug(f"Deleted local image file {filepath} after upload.")
                except Exception as e:
                    self.logger.error(f"Failed to delete local image file {filepath}: {e}")
            else:
                self.logger.info(f"Keeping local image file {filepath} (--keep-images flag set).")

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

    def get_target_radec_and_rates(self, satellite_data, seconds_from_now: float = 0.0):
        ground_station, satellite, ts = self._get_skyfield_ground_station_and_satellite(satellite_data)
        difference = satellite - ground_station
        days_to_add = seconds_from_now / (24 * 60 * 60)  # Skyfield uses days
        topocentric = difference.at(ts.now() + days_to_add)
        target_ra, target_dec, _ = topocentric.radec()

        # determine ra/dec travel rates
        rates = topocentric.frame_latlon_and_rates(
            ground_station
        )  # TODO can this be collapsed with .radec() call above?
        target_dec_rate = rates[4]
        target_ra_rate = rates[3]

        return target_ra, target_dec, target_ra_rate, target_dec_rate

    def predict_slew_time_seconds(self, satellite_data, seconds_from_now: float = 0.0) -> float:
        current_scope_ra, current_scope_dec = self.hardware_adapter.get_telescope_direction()
        current_target_ra, current_target_dec, _, _ = self.get_target_radec_and_rates(satellite_data, seconds_from_now)

        ra_diff_deg = abs((current_target_ra.degrees - current_scope_ra))  # type: ignore
        dec_diff_deg = abs(current_target_dec.degrees - current_scope_dec)  # type: ignore

        if ra_diff_deg > dec_diff_deg:
            return ra_diff_deg / self.hardware_adapter.scope_slew_rate_degrees_per_second
        else:
            return dec_diff_deg / self.hardware_adapter.scope_slew_rate_degrees_per_second

    def point_to_lead_position(self, satellite_data):

        self.logger.debug(f"Using TLE {satellite_data['most_recent_elset']['tle']}")

        max_angular_distance_deg = 0.3
        attempts = 0
        max_attempts = 10
        while attempts < max_attempts:
            attempts += 1
            # Estimate lead position and slew time
            lead_ra, lead_dec, est_slew_time = self.estimate_lead_position(satellite_data)
            self.logger.info(
                f"Pointing ahead to RA: {lead_ra.hours:.4f}h, DEC: {lead_dec.degrees:.4f}°, estimated slew time: {est_slew_time:.1f}s"
            )

            # Move the scope
            slew_start_time = time.time()
            self.hardware_adapter.point_telescope(lead_ra.hours, lead_dec.degrees)  # type: ignore
            while self.hardware_adapter.telescope_is_moving():
                self.logger.debug(f"Slewing to lead position for {satellite_data['name']}...")
                time.sleep(0.1)

            slew_duration = time.time() - slew_start_time
            self.logger.info(
                f"Telescope slew done, took {slew_duration:.1f} sec, off by {abs(slew_duration - est_slew_time):.1f} sec."
            )

            # check our alignment against the starfield
            # is_aligned = self.hardware_adapter.perform_alignment(lead_ra.degrees, lead_dec.degrees)  # type: ignore
            # if not is_aligned:
            #     continue  # try again with the new alignment offsets

            # Check angular distance to satellite's current position
            current_scope_ra, current_scope_dec = self.hardware_adapter.get_telescope_direction()
            current_satellite_position = self.get_target_radec_and_rates(satellite_data)
            current_angular_distance_deg = self.hardware_adapter.angular_distance(
                current_scope_ra,
                current_scope_dec,
                current_satellite_position[0].degrees,  # type: ignore
                current_satellite_position[1].degrees,  # type: ignore
            )
            self.logger.info(f"Current angular distance to satellite is {current_angular_distance_deg:.3f} degrees.")
            if current_angular_distance_deg <= max_angular_distance_deg:
                self.logger.info("Telescope is within acceptable range of target.")
                break

    def estimate_lead_position(
        self,
        satellite_data: dict,
        max_iterations: int = 5,
        tolerance: float = 0.1,
    ):
        """
        Iteratively estimate the future RA/Dec where the satellite will be when the telescope finishes slewing.

        Args:
            satellite_data: Satellite data dict.
            max_iterations: Maximum number of iterations.
            tolerance: Convergence threshold in seconds.

        Returns:
            Tuple of (target_ra, target_dec, estimated_slew_time)
        """
        # Get initial estimate
        est_slew_time = self.predict_slew_time_seconds(satellite_data)
        for _ in range(max_iterations):
            future_radec = self.get_target_radec_and_rates(satellite_data, est_slew_time)
            try:
                new_slew_time = self.predict_slew_time_seconds(satellite_data, est_slew_time)
            except TypeError:
                # Fallback for legacy predict_slew_time_seconds signature
                new_slew_time = self.predict_slew_time_seconds(satellite_data)
            if abs(new_slew_time - est_slew_time) < tolerance:
                break
            est_slew_time = new_slew_time
        return future_radec[0], future_radec[1], est_slew_time
