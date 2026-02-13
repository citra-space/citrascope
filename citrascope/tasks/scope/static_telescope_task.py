import time

from citrascope.hardware.abstract_astro_hardware_adapter import ObservationStrategy
from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class StaticTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):

        self.task.set_status_msg("Fetching satellite data...")
        satellite_data = self.fetch_satellite()
        if not satellite_data or satellite_data.get("most_recent_elset") is None:
            raise ValueError("Could not fetch valid satellite data or TLE.")

        filepath = None
        try:
            if self.hardware_adapter.get_observation_strategy() == ObservationStrategy.MANUAL:
                self.task.set_status_msg("Slewing to target...")
                self.point_to_lead_position(satellite_data)
                self.task.set_status_msg("Exposing image (2s)...")
                filepaths = self.hardware_adapter.take_image(self.task.id, 2.0)  # 2 second exposure

            if self.hardware_adapter.get_observation_strategy() == ObservationStrategy.SEQUENCE_TO_CONTROLLER:
                # Calculate current satellite position and add to satellite_data
                target_ra, target_dec, _, _ = self.get_target_radec_and_rates(satellite_data)
                satellite_data["ra"] = target_ra.degrees
                satellite_data["dec"] = target_dec.degrees

                # Sequence-based adapters handle pointing and tracking themselves
                self.task.set_status_msg("Running observation sequence...")
                filepaths = self.hardware_adapter.perform_observation_sequence(self.task, satellite_data)
        except RuntimeError as e:
            # Filter errors and other hardware errors
            self.logger.error(f"Observation failed for task {self.task.id}: {e}")
            raise

        # Take the image
        return self.upload_image_and_mark_complete(filepaths)
