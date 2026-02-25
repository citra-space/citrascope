from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class TrackingTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):

        self.task.set_status_msg("Fetching satellite data...")
        satellite_data = self.fetch_satellite()
        if not satellite_data or satellite_data.get("most_recent_elset") is None:
            raise ValueError("Could not fetch valid satellite data or TLE.")

        self.task.set_status_msg("Slewing to target...")
        try:
            self.point_to_lead_position(satellite_data)
        except RuntimeError as e:
            self.logger.error(f"Observation failed for task {self.task.id}: {e}")
            return False

        # determine appropriate tracking rates based on satellite motion
        _, _, target_ra_rate, target_dec_rate = self.get_target_radec_and_rates(satellite_data)

        # Set the telescope tracking rates
        self.task.set_status_msg("Setting tracking rates...")
        tracking_set = self.hardware_adapter.set_custom_tracking_rate(
            target_ra_rate.arcseconds.per_second,  # type: ignore[attr-defined]
            target_dec_rate.arcseconds.per_second,  # type: ignore[attr-defined]
        )
        if not tracking_set:
            self.logger.error("Failed to set tracking rates on telescope.")
            return False

        # Take the image
        self.task.set_status_msg("Exposing image (20s)...")
        filepath = self.hardware_adapter.take_image(self.task.id, 20.0)  # 20 second exposure
        return self.upload_image_and_mark_complete(filepath)
