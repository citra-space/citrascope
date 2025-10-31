import time

from citrascope.tasks.scope.base_telescope_task import AbstractBaseTelescopeTask


class StaticTelescopeTask(AbstractBaseTelescopeTask):
    def execute(self):
        satellite_data = self.fetch_satellite()
        if not satellite_data or satellite_data.get("most_recent_elset") is None:
            raise ValueError("Could not fetch valid satellite data or TLE.")

        self.logger.debug(f"Using TLE {satellite_data['most_recent_elset']['tle']}")

        max_angular_distance_deg = 0.3
        attempts = 0
        max_attempts = 10
        while attempts < max_attempts:
            attempts += 1
            # Estimate lead position and slew time
            lead_ra, lead_dec, est_slew_time = self.estimate_lead_position(satellite_data)
            self.logger.info(
                f"Pointing ahead to RA: {lead_ra.hours:.4f}h, DEC: {lead_dec.degrees:.4f}°, estimated slew time: {est_slew_time:.1f}s"
            )

            # Move the scope
            slew_start_time = time.time()
            self.hardware_adapter.point_telescope(lead_ra.hours, lead_dec.degrees)
            while self.hardware_adapter.telescope_is_moving():
                self.logger.debug(f"Slewing to lead position for {satellite_data['name']}...")
                time.sleep(0.1)

            slew_duration = time.time() - slew_start_time
            self.logger.info(
                f"Telescope slew done, took {slew_duration:.1f} sec, off by {abs(slew_duration - est_slew_time):.1f} sec."
            )

            # Check angular distance to satellite's current position
            current_scope_ra, current_scope_dec = self.hardware_adapter.get_telescope_direction()
            current_satellite_position = self.get_target_radec(satellite_data)
            current_angular_distance_deg = self.hardware_adapter.angular_distance(
                current_scope_ra,
                current_scope_dec,
                current_satellite_position[0].degrees,
                current_satellite_position[1].degrees,
            )
            self.logger.info(f"Current angular distance to satellite is {current_angular_distance_deg:.3f} degrees.")
            if current_angular_distance_deg <= max_angular_distance_deg:
                self.logger.info("Telescope is within acceptable range of target.")
                break

        # Take the image
        filepath = self.hardware_adapter.take_image(self.task.id, 2.0)  # 2 second exposure
        return self.upload_image_and_mark_complete(filepath)
