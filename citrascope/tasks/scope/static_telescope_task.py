import time

from citrascope.hardware.abstract_astro_hardware_adapter import ObservationStrategy
from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class StaticTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):

        satellite_data = self.fetch_satellite()
        if not satellite_data or satellite_data.get("most_recent_elset") is None:
            raise ValueError("Could not fetch valid satellite data or TLE.")

        filepath = None
        if self.hardware_adapter.get_observation_strategy() == ObservationStrategy.MANUAL:
            self.point_to_lead_position(satellite_data)
            filepaths = self.hardware_adapter.take_image(self.task.id, 2.0)  # 2 second exposure

        if self.hardware_adapter.get_observation_strategy() == ObservationStrategy.SEQUENCE_TO_CONTROLLER:
            # Assume the hardware adapter has already pointed the telescope and started tracking
            filepaths = self.hardware_adapter.perform_observation_sequence(self.task.id, satellite_data)

        # Take the image
        return self.upload_image_and_mark_complete(filepaths)
