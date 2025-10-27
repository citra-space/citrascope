import time

from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class StaticTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self, tolerance_deg: float = 0.05, max_iterations: int = 5):
        satellite_data, most_recent_elset = self.fetch_satellite_and_elset()
        if not satellite_data or not most_recent_elset:
            return False
        self.logger.info(f"Using TLE {most_recent_elset['tle']}")
        sat_name = satellite_data["name"]
        for attempt in range(max_iterations):
            target_ra, target_dec, _ = self.get_target_radec(satellite_data, most_recent_elset)
            self.logger.info(
                f"Static shot: Slewing telescope to RA: {target_ra} hours, DEC: {target_dec} degrees for {sat_name} (attempt {attempt+1})"
            )
            self.hardware_adapter.point_telescope(target_ra.hours, target_dec.degrees)
            while self.hardware_adapter.telescope_is_moving():
                self.logger.info(f"Scope moving towards {sat_name}...")
                time.sleep(1)
            # Get current telescope position
            current_ra, current_dec = self.hardware_adapter.get_telescope_direction()
            target_ra, target_dec, _ = self.get_target_radec(
                satellite_data, most_recent_elset
            )  ## get where object should be now...
            # Compute pointing error in degrees
            ra_error = abs(current_ra - target_ra.hours) * 15  # RA in hours, convert to degrees
            dec_error = abs(current_dec - target_dec.degrees)
            total_error = (ra_error**2 + dec_error**2) ** 0.5
            self.logger.info(
                f"Pointing error after slew: {total_error:.3f} deg (RA error: {ra_error:.3f}, DEC error: {dec_error:.3f})"
            )
            if total_error <= tolerance_deg:
                self.logger.info(f"Telescope within {tolerance_deg} deg of target. Taking image.")
                break
            else:
                self.logger.info(f"Telescope not within tolerance, re-slewing to updated position.")
        else:
            self.logger.warning(f"Max iterations reached, proceeding to image with current pointing.")
        filepath = self.hardware_adapter.take_image(self.task.id)
        return self.upload_image_and_mark_complete(filepath)
