import base64
import os
import sys
import time

import requests

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter, ObservationStrategy


class NinaAdvancedHttpAdapter(AbstractAstroHardwareAdapter):
    """HTTP adapter for controlling astronomical equipment through N.I.N.A. (Nighttime Imaging 'N' Astronomy) Advanced API.
    https://bump.sh/christian-photo/doc/advanced-api/"""

    DEFAULT_FOCUS_POSITION = 9000

    def __init__(
        self,
        LOGGER,
        url_prefix="http://nina:1888/v2/api",
        scp_command_template="pwd",
        cam_url="/equipment/camera/",
        filterwheel_url="/equipment/filterwheel/",
        focuser_url="/equipment/focuser/",
        mount_url="/equipment/mount/",
        safetymon_url="/equipment/safetymonitor/",
        sequence_url="/sequence/",
        bypass_autofocus=False,
    ):
        super().__init__()
        self.logger = LOGGER
        self.url_prefix = url_prefix
        self.scp_command_template = scp_command_template
        self.cam_url = cam_url
        self.filterwheel_url = filterwheel_url
        self.focuser_url = focuser_url
        self.mount_url = mount_url
        self.safetymon_url = safetymon_url
        self.sequence_url = sequence_url
        self.bypass_autofocus = bypass_autofocus

        self.filter_map = {}
        self.focus_g = self.DEFAULT_FOCUS_POSITION
        self.focus_r = self.DEFAULT_FOCUS_POSITION
        self.focus_i = self.DEFAULT_FOCUS_POSITION
        self.focus_z = self.DEFAULT_FOCUS_POSITION
        self.focus_clear = self.DEFAULT_FOCUS_POSITION

    def do_autofocus(self):

        self.logger.info("Performing autofocus routine ...")
        # move telescope to bright star and start autofocus
        # Mirach ra=(1+9/60.+47.45/3600.)*15 dec=(35+37/60.+11.1/3600.)
        ra = (1 + 9 / 60.0 + 47.45 / 3600.0) * 15
        dec = 35 + 37 / 60.0 + 11.1 / 3600.0

        self.logger.info("Slewing to Mirach ...")
        mount_status = requests.get(self.url_prefix + self.mount_url + "slew?ra=" + str(ra) + "&dec=" + str(dec)).json()
        self.logger.info(f"Mount {mount_status['Response']}")

        # wait for slew to complete
        while self.telescope_is_moving():
            self.logger.info("Waiting for mount to finish slewing...")
            time.sleep(5)

        for id, filter in self.filter_map.items():
            self.logger.info(f"Focusing Filter ID: {id}, Name: {filter['name']}")
            focus_value = self._auto_focus_one_filter(id, filter["name"])
            self.filter_map[id]["focus_position"] = focus_value

    # autofocus routine
    def _auto_focus_one_filter(self, filter_id, filter_name) -> int:

        # change to the requested filter
        correct_filter_in_place = False
        while not correct_filter_in_place:
            requests.get(self.url_prefix + self.filterwheel_url + "change-filter?filterId=" + str(filter_id))
            filterwheel_status = requests.get(self.url_prefix + self.filterwheel_url + "info").json()
            current_filter_id = filterwheel_status["Response"]["SelectedFilter"]["Id"]
            if current_filter_id == filter_id:
                correct_filter_in_place = True
            else:
                self.logger.info(f"Waiting for filterwheel to change to filter ID {filter_id} ...")
                time.sleep(5)

        # move to starting focus position
        self.logger.info("Moving focus to autofocus starting position ...")
        starting_focus_position = self.DEFAULT_FOCUS_POSITION
        is_in_starting_position = False
        while not is_in_starting_position:
            focuser_status = requests.get(
                self.url_prefix + self.focuser_url + "move?position=" + str(starting_focus_position)
            ).json()
            focuser_status = requests.get(self.url_prefix + self.focuser_url + "info").json()
            if int(focuser_status["Response"]["Position"]) == starting_focus_position:
                is_in_starting_position = True
            else:
                self.logger.info("Waiting for focuser to reach starting position ...")
                time.sleep(5)

        # start autofocus
        self.logger.info("Starting autofocus ...")
        focuser_status = requests.get(self.url_prefix + self.focuser_url + "auto-focus").json()
        self.logger.info(f"Focuser {focuser_status['Response']}")

        last_completed_autofocus = requests.get(self.url_prefix + self.focuser_url + "last-af").json()

        if not last_completed_autofocus.get("Success"):
            self.logger.error(f"Failed to start autofocus: {focuser_status.get('Error')}")
            self.logger.warning("Using default focus position")
            return starting_focus_position

        while (
            last_completed_autofocus["Response"]["Filter"] != filter_name
            or last_completed_autofocus["Response"]["InitialFocusPoint"]["Position"] != starting_focus_position
        ):
            self.logger.info("Waiting autofocus")
            last_completed_autofocus = requests.get(self.url_prefix + self.focuser_url + "last-af").json()
            time.sleep(15)

        autofocused_position = focuser_status["Response"]["CalculatedFocusPoint"]["Position"]
        autofocused_value = focuser_status["Response"]["CalculatedFocusPoint"]["Value"]

        self.logger.info(
            f"Autofocus complete for filter {filter_name}: Position {autofocused_position}, HFR {autofocused_value}"
        )
        return autofocused_position

    def _do_point_telescope(self, ra: float, dec: float):
        self.logger.info(f"Slewing to RA: {ra}, Dec: {dec}")
        slew_response = requests.get(f"{self.url_prefix}{self.mount_url}slew?ra={ra}&dec={dec}").json()

        if slew_response.get("Success"):
            self.logger.info(f"Mount slew initiated: {slew_response['Response']}")
            return True
        else:
            self.logger.error(f"Failed to slew mount: {slew_response.get('Error')}")
            return False

    def connect(self) -> bool:
        try:
            # start connection to all equipments
            self.logger.info("Connecting camera ...")
            cam_status = requests.get(self.url_prefix + self.cam_url + "connect").json()
            if not cam_status["Success"]:
                self.logger.error(f"Failed to connect camera: {cam_status.get('Error')}")
                return False
            self.logger.info(f"Camera Connected!")

            self.logger.info("Starting camera cooling ...")
            cool_status = requests.get(self.url_prefix + self.cam_url + "cool").json()
            if not cool_status["Success"]:
                self.logger.warning(f"Failed to start camera cooling: {cool_status.get('Error')}")
            else:
                self.logger.info("Cooler started!")

            self.logger.info("Connecting filterwheel ...")
            filterwheel_status = requests.get(self.url_prefix + self.filterwheel_url + "connect").json()
            if not filterwheel_status["Success"]:
                self.logger.warning(f"Failed to connect filterwheel: {filterwheel_status.get('Error')}")
            else:
                self.logger.info(f"Filterwheel Connected!")

            self.logger.info("Connecting focuser ...")
            focuser_status = requests.get(self.url_prefix + self.focuser_url + "connect").json()
            if not focuser_status["Success"]:
                self.logger.warning(f"Failed to connect focuser: {focuser_status.get('Error')}")
            else:
                self.logger.info(f"Focuser Connected!")

            self.logger.info("Connecting mount ...")
            mount_status = requests.get(self.url_prefix + self.mount_url + "connect").json()
            if not mount_status["Success"]:
                self.logger.error(f"Failed to connect mount: {mount_status.get('Error')}")
                return False
            self.logger.info(f"Mount Connected!")

            self.logger.info("Unparking mount ...")
            mount_status = requests.get(self.url_prefix + self.mount_url + "unpark").json()
            if not mount_status["Success"]:
                self.logger.error(f"Failed to unpark mount: {mount_status.get('Error')}")
                return False
            self.logger.info(f"Mount Unparked!")

            # make a map of available filters and their focus positions
            self.discover_filters()
            if not self.bypass_autofocus:
                self.do_autofocus()
            else:
                self.logger.info("Bypassing autofocus routine as requested")

            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to NINA Advanced API: {e}")
            return False

    def discover_filters(self):
        self.logger.info("Discovering filters ...")
        filterwheel_info = requests.get(self.url_prefix + self.filterwheel_url + "info").json()
        if not filterwheel_info.get("Success"):
            self.logger.error(f"Failed to get filterwheel info: {filterwheel_info.get('Error')}")
            raise RuntimeError("Failed to get filterwheel info")

        filters = filterwheel_info["Response"]["AvailableFilters"]
        for filter in filters:
            filter_id = filter["Id"]
            filter_name = filter["Name"]
            self.filter_map[filter_id] = {"name": filter_name, "focus_position": self.DEFAULT_FOCUS_POSITION}
            self.logger.info(f"Discovered filter: {filter_name} with ID: {filter_id}")

    def disconnect(self):
        pass

    def list_devices(self) -> list[str]:
        return []

    def select_telescope(self, device_name: str) -> bool:
        return True

    def get_telescope_direction(self) -> tuple[float, float]:
        mount_info = requests.get(self.url_prefix + self.mount_url + "info").json()
        if mount_info.get("Success"):
            ra_degrees = mount_info["Response"]["Coordinates"]["RADegrees"]
            dec_degrees = mount_info["Response"]["Coordinates"]["Dec"]
            return (ra_degrees, dec_degrees)
        else:
            self.logger.error(f"Failed to get telescope direction: {mount_info.get('Error')}")
            raise RuntimeError(f"Failed to get mount info: {mount_info.get('Error')}")

    def telescope_is_moving(self) -> bool:
        mount_info = requests.get(self.url_prefix + self.mount_url + "info").json()
        if mount_info.get("Success"):
            return mount_info["Response"]["Slewing"]
        else:
            self.logger.error(f"Failed to get telescope status: {mount_info.get('Error')}")
            return False

    def select_camera(self, device_name: str) -> bool:
        return True

    def take_image(self, task_id: str, exposure_duration_seconds=1) -> str:
        raise NotImplementedError

    def set_custom_tracking_rate(self, ra_rate: float, dec_rate: float):
        pass  # TODO: make real

    def get_tracking_rate(self) -> tuple[float, float]:
        return (0, 0)  # TODO: make real

    def perform_alignment(self, target_ra: float, target_dec: float) -> bool:
        return True  # TODO: make real

    def _get_sequence_template(self) -> str:
        """Load the sequence template as a string for placeholder replacement."""
        template_path = os.path.join(os.path.dirname(__file__), "nina_adv_http_survey_template.json")
        with open(template_path, "r") as f:
            return f.read()

    def get_observation_strategy(self) -> ObservationStrategy:
        return ObservationStrategy.SEQUENCE_TO_CONTROLLER

    def perform_observation_sequence(self, task_id, satellite_data) -> str | list[str]:
        """Create and execute a NINA sequence for the given satellite.

        Args:
            task_id: Unique identifier for this observation task
            satellite_data: Satellite data including TLE information

        Returns:
            str: Path to the captured image
        """
        elset = satellite_data["most_recent_elset"]

        # Load template as string
        template_str = self._get_sequence_template()

        nina_sequence_name = f"Citra Target: {satellite_data["name"]}, Task: {task_id}"

        # Replace placeholders with actual values
        tle_data = f"{elset['tle'][0]}\n{elset['tle'][1]}"
        template_str = template_str.replace("{{SEQUENCE_NAME}}", nina_sequence_name)
        template_str = template_str.replace("{{TLE_DATA}}", tle_data)
        template_str = template_str.replace("{{TLE_LINE1}}", elset["tle"][0])
        template_str = template_str.replace("{{TLE_LINE2}}", elset["tle"][1])
        template_str = template_str.replace("{{SATELLITE_NAME}}", satellite_data["name"])
        template_str = template_str.replace("{{FOCUS_CLEAR}}", str(self.focus_clear))
        template_str = template_str.replace("{{FOCUS_G}}", str(self.focus_g))
        template_str = template_str.replace("{{FOCUS_R}}", str(self.focus_r))
        template_str = template_str.replace("{{FOCUS_I}}", str(self.focus_i))
        template_str = template_str.replace("{{FOCUS_Z}}", str(self.focus_z))

        # Save customized sequence locally
        sequence_filename = f"nina_sequence_{task_id}.json"
        with open(sequence_filename, "w") as f:
            f.write(template_str)

        self.logger.info(f"Created NINA sequence file: {sequence_filename}")

        # Copy sequence to NINA computer
        scp_cmd = self.scp_command_template.format(sequence_filename=sequence_filename)
        result = os.system(scp_cmd)
        if result != 0:
            self.logger.error(f"Failed to copy sequence to NINA: exit code {result}")
            sys.exit(1)
            raise RuntimeError("Failed to copy sequence file to NINA")

        self.logger.info(f"Copied sequence to NINA computer")

        # Clean up local sequence file
        try:
            os.remove(sequence_filename)
            self.logger.info(f"Deleted local sequence file: {sequence_filename}")
        except OSError as e:
            self.logger.warning(f"Failed to delete local sequence file {sequence_filename}: {e}")

        # Load and start the sequence
        sequence_name = sequence_filename.replace(".json", "")

        load_response = requests.get(f"{self.url_prefix}{self.sequence_url}load?sequenceName={sequence_name}").json()
        if not load_response.get("Success"):
            self.logger.error(f"Failed to load sequence: {load_response.get('Error')}")
            raise RuntimeError("Failed to load NINA sequence")

        self.logger.info(f"Loaded sequence: {sequence_name}")

        start_response = requests.get(
            f"{self.url_prefix}{self.sequence_url}start?skipValidation=true"
        ).json()  # TODO: try and fix validation issues
        if not start_response.get("Success"):
            self.logger.error(f"Failed to start sequence: {start_response.get('Error')}")
            raise RuntimeError("Failed to start NINA sequence")

        self.logger.info(f"Started NINA sequence")

        timeout_minutes = 60
        poll_interval_seconds = 10
        elapsed_time = 0
        status_response = None
        while elapsed_time < timeout_minutes * 60:
            status_response = requests.get(f"{self.url_prefix}{self.sequence_url}json").json()

            start_status = status_response["Response"][1][
                "Status"
            ]  # these are also based on the hardcoded template sections for now...
            targets_status = status_response["Response"][2]["Status"]
            end_status = status_response["Response"][3]["Status"]
            self.logger.debug(f"Sequence status - Start: {start_status}, Targets: {targets_status}, End: {end_status}")

            if start_status == "FINISHED" and targets_status == "FINISHED" and end_status == "FINISHED":
                self.logger.info(f"NINA sequence completed")
                break

            self.logger.info(f"NINA sequence still running, waiting {poll_interval_seconds} seconds...")
            time.sleep(poll_interval_seconds)
            elapsed_time += poll_interval_seconds
        else:
            self.logger.error(f"NINA sequence did not complete within timeout of {timeout_minutes} minutes")
            raise RuntimeError("NINA sequence timeout")

        # get a list of images taken in the sequence
        self.logger.info(f"Retrieving list of images taken in sequence...")
        images_response = requests.get(f"{self.url_prefix}/image-history?all=true").json()
        if not images_response.get("Success"):
            self.logger.error(f"Failed to get images list: {images_response.get('Error')}")
            raise RuntimeError("Failed to get images list from NINA")

        images_to_download = []
        expected_image_count = 5  # based on the number of filters in the sequence, need to make dynamic later
        images_found = len(images_response["Response"])
        self.logger.info(
            f"Found {images_found} images in NINA image history, considering the last {expected_image_count}"
        )
        start_index = max(0, images_found - expected_image_count)
        end_index = images_found
        if images_found < expected_image_count:
            self.logger.warning(f"Fewer images found ({images_found}) than expected ({expected_image_count})")
        for i in range(start_index, end_index):
            images_to_download.append(i)
        # TODO: add verification that these images correspond to the current sequence, coming soon:
        # https://github.com/christian-photo/ninaAPI/pull/74

        # Get the most recent image from NINA (index 0) in raw FITS format
        filepaths = []
        for image_index in images_to_download:
            self.logger.info(f"Retrieving image from NINA...")
            image_response = requests.get(
                f"{self.url_prefix}/image/{image_index}",
                params={"raw_fits": "true"},
            )

            if image_response.status_code != 200:
                self.logger.error(f"Failed to retrieve image: HTTP {image_response.status_code}")
                raise RuntimeError("Failed to retrieve image from NINA")

            image_data = image_response.json()
            if not image_data.get("Success"):
                self.logger.error(f"Failed to get image: {image_data.get('Error')}")
                raise RuntimeError(f"Failed to get image from NINA: {image_data.get('Error')}")

            # Decode base64 FITS data and save to file
            fits_base64 = image_data["Response"]
            fits_bytes = base64.b64decode(fits_base64)

            os.makedirs("images", exist_ok=True)
            filepath = f"images/citra_task_{task_id}_image_{image_index}.fits"
            filepaths.append(filepath)

            with open(filepath, "wb") as f:
                f.write(fits_bytes)

            self.logger.info(f"Saved FITS image to {filepath}")

        return filepaths
