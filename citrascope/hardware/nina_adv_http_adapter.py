import json
import os
import time

import requests

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter


class NinaAdvancedHttpAdapter(AbstractAstroHardwareAdapter):
    """HTTP adapter for controlling astronomical equipment through N.I.N.A. (Nighttime Imaging 'N' Astronomy) Advanced API.
    https://bump.sh/christian-photo/doc/advanced-api/"""

    def __init__(
        self,
        LOGGER,
        url_prefix="http://nina:1888/v2/api",
        cam_url="/equipment/camera/",
        filterwheel_url="/equipment/filterwheel/",
        focuser_url="/equipment/focuser/",
        mount_url="/equipment/mount/",
        safetymon_url="/equipment/safetymonitor/",
        sequence_url="/sequence/",
    ):
        super().__init__()
        self.logger = LOGGER
        self.url_prefix = url_prefix
        self.cam_url = cam_url
        self.filterwheel_url = filterwheel_url
        self.focuser_url = focuser_url
        self.mount_url = mount_url
        self.safetymon_url = safetymon_url
        self.sequence_url = sequence_url

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
        self.logger.info("Mount ", mount_status["Response"])

        time.sleep(60)

        focus_g, psf_g = self._auto_focus_one_filter("g", 9000)
        self.logger.info("Focus g: ", focus_g, "PSF g: ", psf_g)
        focus_r, psf_r = self._auto_focus_one_filter("r", 9000)
        self.logger.info("Focus r: ", focus_r, "PSF r: ", psf_r)
        focus_i, psf_i = self._auto_focus_one_filter("i", 9000)
        self.logger.info("Focus i: ", focus_i, "PSF i: ", psf_i)
        focus_z, psf_z = self._auto_focus_one_filter("z-s", 9000)
        self.logger.info("Focus z: ", focus_z, "PSF z: ", psf_z)
        focus_clear, psf_clear = self._auto_focus_one_filter("Clear", 8000)
        self.logger.info("Focus clear: ", focus_clear, "PSF clear: ", psf_clear)

        self.logger.info("Clear: ", focus_clear, " HFR: ", psf_clear)
        self.logger.info("g: ", focus_g, " HFR: ", psf_g)
        self.logger.info("r: ", focus_r, " HFR: ", psf_r)
        self.logger.info("i: ", focus_i, " HFR: ", psf_i)
        self.logger.info("z: ", focus_z, " HFR: ", psf_z)

    # autofocus routine
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
        self.logger.info("Filterwheel ", filterwheel_status["Response"])

        # get filter value
        filterwheel_status = requests.get(self.url_prefix + self.filterwheel_url + "info").json()

        while filterId != filterwheel_status["Response"]["SelectedFilter"]["Id"]:
            self.logger.info("Waiting filterwheel moving")
            filterwheel_status = requests.get(self.url_prefix + self.filterwheel_url + "info").json()
            time.sleep(5)

        self.logger.info("Moving focus ...")
        focuser_status = requests.get(self.url_prefix + self.focuser_url + "move?position=" + str(fcpos)).json()
        self.logger.info("Focuser ", focuser_status["Response"])

        # get focus value
        focuser_status = requests.get(self.url_prefix + self.focuser_url + "info").json()
        # focuser_status['Response']['Position']

        while fcpos != focuser_status["Response"]["Position"]:
            self.logger.info("Waiting focus moving")
            focuser_status = requests.get(self.url_prefix + self.focuser_url + "info").json()
            time.sleep(5)

        self.logger.info("Focus value at:", focuser_status["Response"]["Position"])
        # start autofocus
        self.logger.info("Starting autofocus ...")
        focuser_status = requests.get(self.url_prefix + self.focuser_url + "auto-focus").json()
        self.logger.info("Focuser ", focuser_status["Response"])
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
        # start connection to all equipments
        self.logger.info("Connecting camera ...")
        cam_status = requests.get(self.url_prefix + self.cam_url + "connect").json()
        self.logger.info("Camera ", cam_status["Response"])

        self.logger.info("Starting camera cooling ...")
        cool_status = requests.get(self.url_prefix + self.cam_url + "cool").json()
        self.logger.info(cool_status["Response"])

        self.logger.info("Connecting filterwheel ...")
        filterwheel_status = requests.get(self.url_prefix + self.filterwheel_url + "connect").json()
        self.logger.info("Filterwheel ", filterwheel_status["Response"])

        self.logger.info("Connecting focuser ...")
        focuser_status = requests.get(self.url_prefix + self.focuser_url + "connect").json()
        self.logger.info("Focuser ", focuser_status["Response"])

        self.logger.info("Connecting mount ...")
        mount_status = requests.get(self.url_prefix + self.mount_url + "connect").json()
        self.logger.info("Mount ", mount_status["Response"])

        self.logger.info("Connecting safetymonitor ...")
        safetymon_status = requests.get(self.url_prefix + self.safetymon_url + "connect").json()
        self.logger.info("Safetymonitor ", safetymon_status["Response"])

        return True

    def disconnect(self):
        pass

    def list_devices(self) -> list[str]:
        return []

    def select_telescope(self, device_name: str) -> bool:
        self.do_autofocus()
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

    def _get_sequence_template(self) -> dict:
        template_path = os.path.join(os.path.dirname(__file__), "nina_adv_http_survey_template.json")
        with open(template_path, "r") as f:
            return json.load(f)
