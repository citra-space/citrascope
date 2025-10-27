import time

from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class TrackingTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):
        satellite_data, most_recent_elset = self.fetch_satellite_and_elset()
        if not satellite_data or not most_recent_elset:
            return False
        target_ra, target_dec, sat_name = self.get_target_radec(satellite_data, most_recent_elset)
        self.logger.info(
            f"Tracking shot: Slewing and tracking {sat_name} at RA: {target_ra} hours, DEC: {target_dec} degrees"
        )
        self.hardware_adapter.point_telescope(target_ra.hours, target_dec.degrees)
        while self.hardware_adapter.telescope_is_moving():
            self.logger.info(f"Tracking {sat_name}...")
            time.sleep(2)
        # Here you could add logic to keep tracking the satellite as it moves
        filepath = self.hardware_adapter.take_image(self.task.id)
        return self.upload_image_and_mark_complete(filepath)
