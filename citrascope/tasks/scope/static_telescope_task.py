import time

from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class StaticTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):

        satellite_data = self.fetch_satellite()
        if not satellite_data or satellite_data.get("most_recent_elset") is None:
            raise ValueError("Could not fetch valid satellite data or TLE.")
        self.point_to_lead_position(satellite_data)

        # Take the image
        filepath = self.hardware_adapter.take_image(self.task.id, 2.0)  # 2 second exposure
        return self.upload_image_and_mark_complete(filepath)
