import time

from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class StaticTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):
        satellite_data = self.fetch_satellite()
        if not satellite_data or satellite_data.get("most_recent_elset") is None:
            raise ValueError("Could not fetch valid satellite data or TLE.")

        self.logger.debug(f"Using TLE {satellite_data['most_recent_elset']['tle']}")

        max_angular_distance_deg = 0.5
        attempts = 0
        max_attempts = 10
        current_angular_distance_deg = None
        while attempts < max_attempts and (
            current_angular_distance_deg is None or current_angular_distance_deg > max_angular_distance_deg
        ):
            attempts += 1
            # estimate slew time
            est_slew_time = self.predict_slew_time_seconds(satellite_data)
            self.logger.info(f"Estimated slew time is {est_slew_time:.1f} sec.")

            future_sat_position = self.get_target_radec(satellite_data)

            # move the scope
            slew_start_time = time.time()
            self.hardware_adapter.point_telescope(future_sat_position[0].hours, future_sat_position[1].degrees)
            while self.hardware_adapter.telescope_is_moving():
                self.logger.info(f"Scope moving towards {satellite_data['name']}...")
                time.sleep(1)

            self.logger.info(
                f"Telescope slew done, took {time.time() - slew_start_time:.1f} sec, off by {abs((time.time() - slew_start_time) - est_slew_time):.1f} sec."
            )

            current_scope_ra, current_scope_dec = self.hardware_adapter.get_telescope_direction()
            current_satellite_position = self.get_target_radec(satellite_data)
            current_angular_distance_deg = self.hardware_adapter.angular_distance(
                current_scope_ra,
                current_scope_dec,
                current_satellite_position[0].degrees,
                current_satellite_position[1].degrees,
            )
            self.logger.info(f"Current angular distance to satellite is {current_angular_distance_deg:.3f} degrees.")

        # shoot your shot
        self.logger.info("Taking image...")
        filepath = self.hardware_adapter.take_image(self.task.id)
        return self.upload_image_and_mark_complete(filepath)
