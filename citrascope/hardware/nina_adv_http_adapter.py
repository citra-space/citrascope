import base64
import os
import time

import requests

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter, ObservationStrategy


class NinaAdvancedHttpAdapter(AbstractAstroHardwareAdapter):
    """HTTP adapter for controlling astronomical equipment through N.I.N.A. (Nighttime Imaging 'N' Astronomy) Advanced API.
    https://bump.sh/christian-photo/doc/advanced-api/"""

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

        self.focus_g = 9000
        self.focus_r = 9000
        self.focus_i = 9000
        self.focus_z = 9000
        self.focus_clear = 8000

    def do_autofocus(self):

        # move telescope to bright star and start autofocus
        # Vega ra=(18+36/60.+56.68/3600.)*15 dec=(38+47/60.+8.4/3600.)
        # ra=(18+36/60.+56.68/3600.)*15
        # dec=(38+47/60.+8.4/3600.)
        # Mirach ra=(1+9/60.+47.45/3600.)*15 dec=(35+37/60.+11.1/3600.)
        ra = (1 + 9 / 60.0 + 47.45 / 3600.0) * 15
        dec = 35 + 37 / 60.0 + 11.1 / 3600.0

        self.logger.info("Slewing to Mirach ...")
        mount_status = requests.get(self.url_prefix + self.mount_url + "slew?ra=" + str(ra) + "&dec=" + str(dec)).json()
        self.logger.info(f"Mount {mount_status['Response']}")

        time.sleep(60)

        self.focus_g, psf_g = self._auto_focus_one_filter("g", 9000)
        self.logger.info(f"Focus g: {self.focus_g} PSF g: {psf_g}")
        self.focus_r, psf_r = self._auto_focus_one_filter("r", 9000)
        self.logger.info(f"Focus r: {self.focus_r} PSF r: {psf_r}")
        self.focus_i, psf_i = self._auto_focus_one_filter("i", 9000)
        self.logger.info(f"Focus i: {self.focus_i} PSF i: {psf_i}")
        self.focus_z, psf_z = self._auto_focus_one_filter("z-s", 9000)
        self.logger.info(f"Focus z: {self.focus_z} PSF z: {psf_z}")
        self.focus_clear, psf_clear = self._auto_focus_one_filter("Clear", 8000)
        self.logger.info(f"Focus clear: {self.focus_clear} PSF clear: {psf_clear}")

        self.logger.info(f"Clear: {self.focus_clear} HFR: {psf_clear}")
        self.logger.info(f"g: {self.focus_g} HFR: {psf_g}")
        self.logger.info(f"r: {self.focus_r} HFR: {psf_r}")
        self.logger.info(f"i: {self.focus_i} HFR: {psf_i}")
        self.logger.info(f"z: {self.focus_z} HFR: {psf_z}")

    # autofocus routine
    # TODO: make this configurable as to which filters are where and what's desired to be included
    def _auto_focus_one_filter(self, filtername: str, fcpos: int) -> tuple[int, int]:
        if filtername == "Clear":
            filterId = 0
        elif filtername == "g":
            filterId = 3
        elif filtername == "r":
            filterId = 2
        elif filtername == "i":
            filterId = 4
        elif filtername == "z-s":
            filterId = 1
        else:
            self.logger.error("Unknown filter")
            exit()

        self.logger.info("Moving filter ...")
        filterwheel_status = requests.get(
            self.url_prefix + self.filterwheel_url + "change-filter?filterId=" + str(filterId)
        ).json()
        self.logger.info(f"Filterwheel {filterwheel_status['Response']}")

        # get filter value
        filterwheel_status = requests.get(self.url_prefix + self.filterwheel_url + "info").json()

        while filterId != filterwheel_status["Response"]["SelectedFilter"]["Id"]:
            self.logger.info("Waiting filterwheel moving")
            filterwheel_status = requests.get(self.url_prefix + self.filterwheel_url + "info").json()
            time.sleep(5)

        self.logger.info("Moving focus ...")
        focuser_status = requests.get(self.url_prefix + self.focuser_url + "move?position=" + str(fcpos)).json()
        self.logger.info(f"Focuser {focuser_status['Response']}")

        # get focus value
        focuser_status = requests.get(self.url_prefix + self.focuser_url + "info").json()
        # focuser_status['Response']['Position']

        while fcpos != focuser_status["Response"]["Position"]:
            self.logger.info("Waiting focus moving")
            focuser_status = requests.get(self.url_prefix + self.focuser_url + "info").json()
            time.sleep(5)

        self.logger.info(f"Focus value at: {focuser_status['Response']['Position']}")
        # start autofocus
        self.logger.info("Starting autofocus ...")
        focuser_status = requests.get(self.url_prefix + self.focuser_url + "auto-focus").json()
        self.logger.info(f"Focuser {focuser_status['Response']}")
        focuser_status = requests.get(self.url_prefix + self.focuser_url + "last-af").json()
        while (
            focuser_status["Response"]["Filter"] != filtername
            or focuser_status["Response"]["InitialFocusPoint"]["Position"] != fcpos
        ):
            self.logger.info("Waiting autofocus")
            focuser_status = requests.get(self.url_prefix + self.focuser_url + "last-af").json()
            time.sleep(30)
        return (
            focuser_status["Response"]["CalculatedFocusPoint"]["Position"],
            focuser_status["Response"]["CalculatedFocusPoint"]["Value"],
        )

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

            # self.logger.info("Connecting safetymonitor ...")
            # safetymon_status = requests.get(self.url_prefix + self.safetymon_url + "connect").json()
            # self.logger.info(f"Safetymonitor {safetymon_status['Response']}")

            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to NINA Advanced API: {e}")
            return False

    def disconnect(self):
        pass

    def list_devices(self) -> list[str]:
        return []

    def select_telescope(self, device_name: str) -> bool:
        if not self.bypass_autofocus:
            self.do_autofocus()
        else:
            self.logger.info("Bypassing autofocus routine as requested")
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

        # Replace placeholders with actual values
        tle_data = f"{elset['tle'][0]}\\n{elset['tle'][1]}"
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
        poll_interval_seconds = 15
        elapsed_time = 0
        while elapsed_time < timeout_minutes * 60:
            status_response = requests.get(f"{self.url_prefix}{self.sequence_url}json").json()

            start_status = status_response["Response"][1][
                "Status"
            ]  # these are also based on the hardcoded template sections for now...
            targets_status = status_response["Response"][2]["Status"]
            end_status = status_response["Response"][3]["Status"]
            self.logger.info(f"Sequence status - Start: {start_status}, Targets: {targets_status}, End: {end_status}")

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
        for i in range(images_found - expected_image_count - 1, images_found):
            possible_image = images_response["Response"][i]
            if possible_image["TargetName"] == satellite_data["name"]:  # not my favorite
                images_to_download.append(i)
            else:
                self.logger.warning(
                    f"Image {i} target name {possible_image['TargetName']} does not match expected {satellite_data['name']}"
                )

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
