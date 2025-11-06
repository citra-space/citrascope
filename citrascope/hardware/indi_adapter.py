import os
import time
from pathlib import Path

import PyIndi
import tetra3
from pixelemon import Telescope, TelescopeImage, TetraSolver
from pixelemon.optics import WilliamsMiniCat51
from pixelemon.optics._base_optical_assembly import BaseOpticalAssembly
from pixelemon.sensors import IMX174
from pixelemon.sensors._base_sensor import BaseSensor

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter


# The IndiClient class which inherits from the module PyIndi.BaseClient class
# Note that all INDI constants are accessible from the module as PyIndi.CONSTANTNAME
class IndiAdapter(PyIndi.BaseClient, AbstractAstroHardwareAdapter):
    # Minimum angular distance (degrees) to consider a move significant for slew rate measurement
    _slew_min_distance_deg: float = 2.0

    our_scope: PyIndi.BaseDevice
    our_camera: PyIndi.BaseDevice

    _current_task_id: str = ""
    _last_saved_filename: str = ""

    _alignment_offset_ra: float = 0.0
    _alignment_offset_dec: float = 0.0

    def __init__(self, CITRA_LOGGER, host: str, port: int):
        super(IndiAdapter, self).__init__()
        self.logger = CITRA_LOGGER
        self.logger.debug("creating an instance of IndiClient")
        self.host = host
        self.port = port

        TetraSolver.high_memory()

    def newDevice(self, d):
        """Emmited when a new device is created from INDI server."""
        self.logger.info(f"new device {d.getDeviceName()}")
        # TODO: if it's the scope we want, set our_scope

    def removeDevice(self, d):
        """Emmited when a device is deleted from INDI server."""
        self.logger.info(f"remove device {d.getDeviceName()}")
        # TODO: if it's our_scope, set our_scope to None, and react accordingly

    def newProperty(self, p):
        """Emmited when a new property is created for an INDI driver."""
        self.logger.debug(f"new property {p.getName()} as {p.getTypeAsString()} for device {p.getDeviceName()}")

    def updateProperty(self, p):
        """Emmited when a new property value arrives from INDI server."""
        self.logger.debug(f"update property {p.getName()} as {p.getTypeAsString()} for device {p.getDeviceName()}")
        if (
            hasattr(self, "our_scope")
            and self.our_scope is not None
            and p.getDeviceName() == self.our_scope.getDeviceName()
        ):
            value = None
            changed_type = p.getTypeAsString()
            if changed_type == "INDI_TEXT":
                value = self.our_scope.getText(p.getName())[0].value
            if changed_type == "INDI_NUMBER":
                value = self.our_scope.getNumber(p.getName())[0].value
            self.logger.debug(f"Scope '{self.our_scope.getDeviceName()}' property {p.getName()} updated value: {value}")

        if p.getType() == PyIndi.INDI_BLOB:
            blobProperty = self.our_camera.getBLOB(p.getName())
            format = blobProperty[0].getFormat()
            bloblen = blobProperty[0].getBlobLen()
            size = blobProperty[0].getSize()
            self.logger.debug(f"Received BLOB of format {format}, size {size}, length {bloblen}")

            # if there's a task underway, save the image to a file
            if self._current_task_id != "":
                os.makedirs("images", exist_ok=True)
                self._last_saved_filename = f"images/citra_task_{self._current_task_id}_image.fits"
                for b in blobProperty:
                    with open(self._last_saved_filename, "wb") as f:
                        f.write(b.getblobdata())
                        self.logger.info(f"Saved {self._last_saved_filename}")
                self._current_task_id = ""

    def removeProperty(self, p):
        """Emmited when a property is deleted for an INDI driver."""
        self.logger.debug(f"remove property {p.getName()} as {p.getTypeAsString()} for device {p.getDeviceName()}")

    def newMessage(self, d, m):
        """Emmited when a new message arrives from INDI server."""
        msg = d.messageQueue(m)
        if "error" in msg.lower():
            self.logger.error(f"new Message {msg}")
        else:
            self.logger.debug(f"new Message {msg}")

    def serverConnected(self):
        """Emmited when the server is connected."""
        self.logger.info(f"INDI Server connected ({self.getHost()}:{self.getPort()})")

    def serverDisconnected(self, code):
        """Emmited when the server gets disconnected."""
        self.logger.info(f"INDI Server disconnected (exit code = {code},{self.getHost()}:{self.getPort()})")

    def newBLOB(self, bp):
        for b in bp:
            with open("image.fits", "wb") as f:
                f.write(b.getblob())
                print("Saved image.fits")

    # ========================= AstroHardwareAdapter Methods =========================

    def connect(self) -> bool:
        self.setServer(self.host, self.port)
        return self.connectServer()

    def list_devices(self):
        names = []
        for device in self.getDevices():
            names.append(device.getDeviceName())
        return names

    def select_telescope(self, device_name: str) -> bool:
        devices = self.getDevices()
        for device in devices:
            if device.getDeviceName() == device_name:
                self.our_scope = device
                return True
        return False

    def disconnect(self):
        self.disconnectServer()

    def _do_point_telescope(self, ra: float, dec: float):
        """Hardware-specific implementation to point the telescope to the specified RA/Dec coordinates."""
        telescope_radec = self.our_scope.getNumber("EQUATORIAL_EOD_COORD")
        new_ra = float(ra)
        new_dec = float(dec)
        telescope_radec[0].setValue(new_ra)  # RA in hours
        telescope_radec[1].setValue(new_dec)  # DEC in degrees
        try:
            self.sendNewNumber(telescope_radec)
        except Exception as e:
            self.logger.error(f"Error sending new RA/DEC to telescope: {e}")
            return

    def get_telescope_direction(self) -> tuple[float, float]:
        """Read the current telescope direction (RA degrees, DEC degrees)."""
        telescope_radec = self.our_scope.getNumber("EQUATORIAL_EOD_COORD")
        self.logger.debug(
            f"Telescope currently pointed to RA: {telescope_radec[0].value * 15.0} degrees, DEC: {telescope_radec[1].value} degrees"
        )
        return telescope_radec[0].value * 15.0, telescope_radec[1].value

    def telescope_is_moving(self) -> bool:
        """Check if the telescope is currently moving."""
        telescope_radec = self.our_scope.getNumber("EQUATORIAL_EOD_COORD")
        return telescope_radec.getState() == PyIndi.IPS_BUSY

    def select_camera(self, device_name: str) -> bool:
        """Select a specific camera by name."""
        devices = self.getDevices()
        for device in devices:
            if device.getDeviceName() == device_name:
                self.our_camera = device
                self.setBLOBMode(PyIndi.B_ALSO, device_name, None)
                return True
        return False

    def take_image(self, task_id: str, exposure_duration_seconds=1.0):
        """Capture an image with the currently selected camera."""

        self.logger.info(f"Taking {exposure_duration_seconds} second exposure...")
        self._current_task_id = task_id
        ccd_exposure = self.our_camera.getNumber("CCD_EXPOSURE")
        ccd_exposure[0].setValue(exposure_duration_seconds)
        self.sendNewNumber(ccd_exposure)

        while self.is_camera_busy() and self._current_task_id != "":
            self.logger.debug("Waiting for camera to finish exposure...")
            time.sleep(0.2)

        filename = self._last_saved_filename
        self._last_saved_filename = ""
        return filename

    def is_camera_busy(self) -> bool:
        """Check if the camera is currently busy taking an image."""
        ccd_exposure = self.our_camera.getNumber("CCD_EXPOSURE")
        return ccd_exposure.getState() == PyIndi.IPS_BUSY

    def set_custom_tracking_rate(self, ra_rate: float, dec_rate: float):
        """Set the tracking rate for the telescope in RA and Dec (arcseconds per second)."""
        self.logger.info(f"Setting tracking rate: RA {ra_rate} arcseconds/s, Dec {dec_rate} arcseconds/s")
        try:

            track_state_prop = self.our_scope.getSwitch("TELESCOPE_TRACK_STATE")
            track_state_prop[0].setState(PyIndi.ISS_OFF)
            self.sendNewSwitch(track_state_prop)

            track_mode_prop = self.our_scope.getSwitch("TELESCOPE_TRACK_MODE")
            track_mode_prop[0].setState(PyIndi.ISS_OFF)  # TRACK_SIDEREAL
            track_mode_prop[1].setState(PyIndi.ISS_OFF)  # TRACK_SOLAR
            track_mode_prop[2].setState(PyIndi.ISS_OFF)  # TRACK_LUNAR
            track_mode_prop[3].setState(PyIndi.ISS_ON)  # TRACK_CUSTOM
            self.sendNewSwitch(track_mode_prop)

            indi_tracking_rate = self.our_scope.getNumber("TELESCOPE_TRACK_RATE")
            self.logger.info(
                f"Current INDI tracking rates: 0: {indi_tracking_rate[0].value} 1: {indi_tracking_rate[1].value}"
            )
            indi_tracking_rate[0].setValue(ra_rate)
            indi_tracking_rate[1].setValue(dec_rate)
            self.sendNewNumber(indi_tracking_rate)

            track_state_prop[0].setState(PyIndi.ISS_ON)  # Turn tracking ON
            self.sendNewSwitch(track_state_prop)
            return True

        except Exception as e:
            self.logger.error(f"Error setting tracking rates: {e}")
            return False

    def get_tracking_rate(self) -> tuple[float, float]:
        """Get the current tracking rate for the telescope in RA and Dec (arcseconds per second)."""
        ra_rate = self.our_scope.getNumber("TELESCOPE_TRACK_RATE_RA")[0].value
        dec_rate = self.our_scope.getNumber("TELESCOPE_TRACK_RATE_DEC")[0].value
        return ra_rate, dec_rate

    def perform_alignment(self, target_ra: float, target_dec: float) -> bool:
        """
        Perform plate-solving-based alignment to adjust the telescope's position.

        Args:
            target_ra (float): The target Right Ascension (RA) in degrees.
            target_dec (float): The target Declination (Dec) in degrees.

        Returns:
            bool: True if alignment was successful, False otherwise.
        """

        # take alignment exposure
        alignment_filename = self.take_image("alignment", 5.0)

        # this needs to be made configurable
        sim_ccd = BaseSensor(
            x_pixel_count=1280,
            y_pixel_count=1024,
            pixel_width=5.86,
            pixel_height=5.86,
        )
        sim_scope = BaseOpticalAssembly(image_circle_diameter=9.2, focal_length=700, focal_ratio=5.8)
        telescope = Telescope(sensor=sim_ccd, optics=sim_scope)
        image = TelescopeImage.from_fits_file(Path(alignment_filename), telescope)

        # this line can be used to read a manually sideloded FITS file for testing
        # image = TelescopeImage.from_fits_file(Path("images/cosmos-2564_10s.fits"), Telescope(sensor=IMX174(), optics=WilliamsMiniCat51()))

        solve = image.plate_solve

        self.logger.debug(f"Plate solving result: {solve}")

        if solve is None:  # type: ignore
            self.logger.error("Plate solving failed.")
            return False

        self.logger.info(
            f"From {solve.number_of_stars} stars, solved RA: {solve.right_ascension:.4f}deg, Solved Dec: {solve.declination:.4f}deg in {solve.solve_time:.2f} ms, "
            + f"false prob: {solve.false_positive_probability}, est fov: {solve.estimated_horizontal_fov:.3f}"
        )
        self._alignment_offset_dec = solve.declination - target_dec
        self._alignment_offset_ra = solve.right_ascension - target_ra

        self.logger.info(
            f"Alignment offsets set to RA: {self._alignment_offset_ra} degrees, Dec: {self._alignment_offset_dec} degrees"
        )

        return True
