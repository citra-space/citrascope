import time

from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class StaticTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):
        satellite_data = self.fetch_satellite()
        if not satellite_data or satellite_data.get("most_recent_elset") is None:
            raise ValueError("Could not fetch valid satellite data or TLE.")

        self.logger.info(f"Using TLE {satellite_data['most_recent_elset']['tle']}")
        sat_name = satellite_data["name"]

        # get predicted position and slew time
        desired_slew_time_margin_sec = 5.0
        estimated_slew_time_sec, (predicted_ra, predicted_dec) = self.get_predicted_slew_time_and_sat_radec(
            satellite_data, desired_slew_time_margin_sec
        )

        # move the scope
        slew_start_time = time.time()
        self.hardware_adapter.point_telescope(predicted_ra.hours, predicted_dec.degrees)
        while self.hardware_adapter.telescope_is_moving():
            self.logger.info(f"Scope moving towards {sat_name}...")
            time.sleep(1)

        current_scope_ra, current_scope_dec = self.hardware_adapter.get_telescope_direction()
        self.logger.info(
            f"Telescope slew done, took {time.time() - slew_start_time:.1f} sec. Pointed to {current_scope_ra:.3f} deg, Dec: {current_scope_dec:.3f}"
        )
        self.logger.info(
            f"Estimated slew time was off by {abs((time.time() - slew_start_time) - estimated_slew_time_sec - desired_slew_time_margin_sec):.1f} sec."
        )

        # while the sat moves, check it has moved within tolerance or is now moving away
        aiming_tolerance_deg = 0.1
        max_iterations = 10
        for iteration in range(max_iterations):
            sat_radec = self.get_target_radec(satellite_data)
            angular_distance_deg = self.hardware_adapter.angular_distance(
                current_scope_ra, current_scope_dec, sat_radec[0].degrees, sat_radec[1].degrees
            )
            self.logger.info(f"Angular distance to target: {angular_distance_deg:.3f} deg")

            if angular_distance_deg <= aiming_tolerance_deg:
                self.logger.info(f"Target within tolerance of {aiming_tolerance_deg} deg.")
                break

            self.logger.info(
                f"Waiting 1 second before re-checking position... (iteration {iteration + 1}/{max_iterations})"
            )
            time.sleep(1)

        # shoot your shot
        self.logger.info("Taking image...")
        filepath = self.hardware_adapter.take_image(self.task.id)
        return self.upload_image_and_mark_complete(filepath)
