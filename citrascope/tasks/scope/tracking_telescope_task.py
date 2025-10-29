import time

from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class TrackingTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):
        sat_data = self.fetch_satellite()
        if not sat_data or not sat_data.get("most_recent_elset"):
            raise ValueError("Could not fetch valid satellite data or TLE.")

        target_ra, target_dec = self.get_target_radec(sat_data)
        self.logger.info(
            f"Tracking shot: Slewing and tracking {sat_data['name']} at RA: {target_ra} hours, DEC: {target_dec} degrees"
        )
        self.hardware_adapter.point_telescope(target_ra.hours, target_dec.degrees)
        while self.hardware_adapter.telescope_is_moving():
            self.logger.info(f"Tracking {sat_data['name']}...")
            time.sleep(2)
        # Here you could add logic to keep tracking the satellite as it moves
        filepath = self.hardware_adapter.take_image(self.task.id)
        return self.upload_image_and_mark_complete(filepath)
