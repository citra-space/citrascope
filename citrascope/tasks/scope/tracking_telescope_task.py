import time

from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class TrackingTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):

        satellite_data = self.fetch_satellite()
        if not satellite_data or satellite_data.get("most_recent_elset") is None:
            raise ValueError("Could not fetch valid satellite data or TLE.")

        self.point_to_lead_position(satellite_data)

        # determine appropriate tracking rates based on satellite motion
        _, _, target_ra_rate, target_dec_rate = self.get_target_radec_and_rates(satellite_data)

        # Set the telescope tracking rates
        tracking_set = self.hardware_adapter.set_custom_tracking_rate(
            target_ra_rate.arcseconds.per_second, target_dec_rate.arcseconds.per_second
        )
        if not tracking_set:
            self.logger.error("Failed to set tracking rates on telescope.")
            return False

        # Take the image
        filepath = self.hardware_adapter.take_image(self.task.id, 20.0)  # 20 second exposure
        return self.upload_image_and_mark_complete(filepath)
