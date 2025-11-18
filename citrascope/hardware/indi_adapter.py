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

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter, ObservationStrategy


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

    def __init__(self, CITRA_LOGGER, host: str, port: int, telescope_name: str = "", camera_name: str = ""):
        super(IndiAdapter, self).__init__()
        self.logger = CITRA_LOGGER
        self.logger.debug("creating an instance of IndiClient")
        self.host = host
        self.port = port
        self.telescope_name = telescope_name
        self.camera_name = camera_name

        # TetraSolver.high_memory()

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
        try:

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
                self.logger.debug(
                    f"Scope '{self.our_scope.getDeviceName()}' property {p.getName()} updated value: {value}"
                )

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
        except Exception as e:
            self.logger.error(f"Error processing updated property {p.getName()}: {e}")

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
        connected = self.connectServer()

        if not connected:
            self.logger.error("Failed to connect to INDI server")
            return False

        time.sleep(1)  # Give server time to enumerate devices

        # Auto-select telescope if name provided
        if self.telescope_name:
            device_list = self.list_devices()
            if self.telescope_name not in device_list:
                self.logger.error(f"Could not find configured telescope ({self.telescope_name}) on INDI server.")
                return False

            if not self.select_telescope(self.telescope_name):
                self.logger.error(f"Failed to select telescope: {self.telescope_name}")
                return False
            self.logger.info(f"Found and connected to telescope: {self.telescope_name}")

        # Auto-select camera if name provided
        if self.camera_name:
            device_list = self.list_devices()
            if self.camera_name not in device_list:
                self.logger.error(f"Could not find configured camera ({self.camera_name}) on INDI server.")
                return False

            if not self.select_camera(self.camera_name):
                self.logger.error(f"Failed to select camera: {self.camera_name}")
                return False
            self.logger.info(f"Found and connected to camera: {self.camera_name}")

        return True

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

                # Connect the telescope device if not already connected
                connect_prop = device.getSwitch("CONNECTION")
                if connect_prop:
                    if not device.isConnected():
                        self.logger.info(f"Connecting telescope device: {device_name}")
                        connect_prop[0].setState(PyIndi.ISS_ON)  # CONNECT
                        connect_prop[1].setState(PyIndi.ISS_OFF)  # DISCONNECT
                        self.sendNewSwitch(connect_prop)
                        time.sleep(1)  # Give device time to connect
                    else:
                        self.logger.debug(f"Telescope device {device_name} already connected")

                return True
        return False

    def disconnect(self):
        self.disconnectServer()

    def _do_point_telescope(self, ra: float, dec: float):
        """Hardware-specific implementation to point the telescope to the specified RA/Dec coordinates."""
        # Check if telescope is selected
        if not hasattr(self, "our_scope") or self.our_scope is None:
            self.logger.error("No telescope selected. Call select_telescope() first.")
            return

        # Get the property
        telescope_radec = self.our_scope.getNumber("EQUATORIAL_EOD_COORD")

        # Check if property exists and is valid
        if not telescope_radec:
            self.logger.error("EQUATORIAL_EOD_COORD property not found on telescope")
            return

        # Check if property is ready (not busy)
        if telescope_radec.getState() == PyIndi.IPS_BUSY:
            self.logger.warning("Telescope is currently busy, waiting for it to be ready...")
            # Could add a wait loop here if needed

        # Check if property has the expected number of elements
        if len(telescope_radec) < 2:
            self.logger.error(f"EQUATORIAL_EOD_COORD has {len(telescope_radec)} elements, expected 2")
            return

        new_ra = float(ra)
        new_dec = float(dec)
        telescope_radec[0].setValue(new_ra)  # RA in hours
        telescope_radec[1].setValue(new_dec)  # DEC in degrees

        try:
            self.sendNewNumber(telescope_radec)
            self.logger.info(f"Sent telescope coordinates: RA={new_ra}h, DEC={new_dec}°")
        except Exception as e:
            self.logger.error(f"Error sending new RA/DEC to telescope: {e}")
            return

    def get_telescope_direction(self) -> tuple[float, float]:
        """Read the current telescope direction (RA degrees, DEC degrees)."""
        # Check if telescope is selected
        if not hasattr(self, "our_scope") or self.our_scope is None:
            self.logger.error("No telescope selected. Call select_telescope() first.")
            return (0.0, 0.0)

        telescope_radec = self.our_scope.getNumber("EQUATORIAL_EOD_COORD")

        if not telescope_radec:
            self.logger.error("EQUATORIAL_EOD_COORD property not found on telescope")
            self.logger.error("Could not read telescope coordinates")
            return (0.0, 0.0)

        if len(telescope_radec) < 2:
            self.logger.error(f"EQUATORIAL_EOD_COORD has {len(telescope_radec)} elements, expected 2")
            self.logger.error("Could not read telescope coordinates")
            return (0.0, 0.0)

        self.logger.debug(
            f"Telescope currently pointed to RA: {telescope_radec[0].value * 15.0} degrees, DEC: {telescope_radec[1].value} degrees"
        )
        return telescope_radec[0].value * 15.0, telescope_radec[1].value

    def telescope_is_moving(self) -> bool:
        """Check if the telescope is currently moving."""
        if not hasattr(self, "our_scope") or self.our_scope is None:
            return False

        telescope_radec = self.our_scope.getNumber("EQUATORIAL_EOD_COORD")

        if not telescope_radec:
            return False

        return telescope_radec.getState() == PyIndi.IPS_BUSY

    def select_camera(self, device_name: str) -> bool:
        """Select a specific camera by name."""
        devices = self.getDevices()
        for device in devices:
            if device.getDeviceName() == device_name:
                self.our_camera = device
                self.setBLOBMode(PyIndi.B_ALSO, device_name, None)

                # Connect the camera device if not already connected
                connect_prop = device.getSwitch("CONNECTION")
                if connect_prop:
                    if not device.isConnected():
                        self.logger.info(f"Connecting camera device: {device_name}")
                        self._set_switch(device, "CONNECTION", "CONNECT")
                        time.sleep(2)  # Give device time to connect
                    else:
                        self.logger.debug(f"Camera device {device_name} already connected")

                # Configure camera parameters
                self._configure_camera_params()

                return True
        return False

    def _configure_camera_params(self):
        """Initialize camera parameters to match EKOS behavior."""
        if not hasattr(self, "our_camera") or self.our_camera is None:
            return

        self._set_switch(self.our_camera, "CONNECTION", "CONNECT")
        self._set_switch(self.our_camera, "CCD_FRAME_TYPE", "FRAME_LIGHT")
        self._set_switch(self.our_camera, "UPLOAD_MODE", "UPLOAD_CLIENT")
        self._set_switch(
            self.our_camera, "CCD_TRANSFER_FORMAT", "FORMAT_FITS"
        )  # No ISwitch '' in CCD Simulator.CCD_TRANSFER_FORMAT..?
        self._set_switch(self.our_camera, "CCD_COMPRESSION", "INDI_DISABLED")

        self._set_numbers(
            self.our_camera,
            "CCD_BINNING",
            {
                "HOR_BIN": 1,
                "VER_BIN": 1,
            },
        )

        # Get CCD_INFO to find max dimensions
        ccd_info = self.our_camera.getNumber("CCD_INFO")
        max_x = None
        max_y = None
        if ccd_info:
            for item in ccd_info:
                if item.getName() == "CCD_MAX_X":
                    max_x = item.value
                elif item.getName() == "CCD_MAX_Y":
                    max_y = item.value

        if max_x and max_y:
            self._set_numbers(
                self.our_camera,
                "CCD_FRAME",
                {
                    "X": 0,
                    "Y": 0,
                    "WIDTH": max_x,
                    "HEIGHT": max_y,
                },
            )

    def _set_switch(self, device, property_name: str, switch_name: str) -> bool:
        svp = device.getSwitch(property_name)
        if svp is None:
            return False

        available_names = [item.getName() for item in svp]
        if switch_name not in available_names:
            self.logger.warning(f"INDI Switch '{property_name}' only supports {available_names}, not '{switch_name}'")
            return False

        # Turn everything OFF
        for item in svp:
            item.setState(PyIndi.ISS_OFF)

        # Turn the desired one ON
        matched = False
        for item in svp:
            item_name = item.getName()
            if item_name == switch_name:
                item.setState(PyIndi.ISS_ON)
                matched = True
                break

        if not matched:
            return False

        # Send updated vector
        result = self.sendNewSwitch(svp)
        return True

    def _set_numbers(self, device, property_name: str, values: dict) -> bool:
        """
        values: { "ELEMENT_NAME": value, ... }
        """
        nvp = device.getNumber(property_name)
        if nvp is None:
            return False

        # Map element names → items
        items = {item.getName(): item for item in nvp}

        # Ensure all requested elements exist
        for name in values.keys():
            if name not in items:
                return False  # or raise

        # Set values
        for name, val in values.items():
            items[name].setValue(float(val))

        # Send once
        result = self.sendNewNumber(nvp)
        return True

    def take_image(self, task_id: str, exposure_duration_seconds=1.0):
        """Capture an image with the currently selected camera."""

        # Check if camera is selected
        if not hasattr(self, "our_camera") or self.our_camera is None:
            self.logger.error("No camera selected. Call select_camera() first.")
            return None

        # Get the CCD_EXPOSURE property
        ccd_exposure = self.our_camera.getNumber("CCD_EXPOSURE")

        # Check if property exists and is valid
        if not ccd_exposure:
            self.logger.error("CCD_EXPOSURE property not found on camera")
            return None

        # Check if property has at least one element
        if len(ccd_exposure) < 1:
            self.logger.error(f"CCD_EXPOSURE has {len(ccd_exposure)} elements, expected at least 1")
            return None

        self.logger.info(f"Taking {exposure_duration_seconds} second exposure...")
        self._current_task_id = task_id

        try:
            ccd_exposure[0].setValue(exposure_duration_seconds)
            self.sendNewNumber(ccd_exposure)
        except Exception as e:
            self.logger.error(f"Error sending exposure command to camera: {e}")
            self._current_task_id = ""
            return None

        while self.is_camera_busy() and self._current_task_id != "":
            self.logger.debug("Waiting for camera to finish exposure...")
            time.sleep(0.2)

        filename = self._last_saved_filename
        self._last_saved_filename = ""
        return filename

    def is_camera_busy(self) -> bool:
        """Check if the camera is currently busy taking an image."""
        # Check if camera is selected
        if not hasattr(self, "our_camera") or self.our_camera is None:
            return False

        ccd_exposure = self.our_camera.getNumber("CCD_EXPOSURE")

        # Check if property exists
        if not ccd_exposure:
            return False

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
        try:

            # take alignment exposure
            alignment_filename = self.take_image("alignment", 5.0)

            if alignment_filename is None:
                self.logger.error("Failed to take alignment image.")
                return False

            # this needs to be made configurable
            sim_ccd = BaseSensor(
                x_pixel_count=1280,
                y_pixel_count=1024,
                pixel_width=5.86,
                pixel_height=5.86,
            )
            sim_scope = BaseOpticalAssembly(image_circle_diameter=9.61, focal_length=300, focal_ratio=6)
            telescope = Telescope(sensor=sim_ccd, optics=sim_scope)
            image = TelescopeImage.from_fits_file(Path(alignment_filename), telescope)

            # this line can be used to read a manually sideloded FITS file for testing
            # image = TelescopeImage.from_fits_file(Path("images/cosmos-2564_10s.fits"), Telescope(sensor=IMX174(), optics=WilliamsMiniCat51()))

            solve = image.plate_solve

            self.logger.debug(f"Plate solving result: {solve}")

            if solve is None:
                self.logger.error("Plate solving failed.")
                return False

            self.logger.info(
                f"From {solve.number_of_stars} stars, solved RA: {solve.right_ascension:.4f}deg, Solved Dec: {solve.declination:.4f}deg in {solve.solve_time:.2f}ms, "
                + f"false prob: {solve.false_positive_probability}, est fov: {solve.estimated_horizontal_fov:.3f}"
            )
            self._alignment_offset_dec = solve.declination - target_dec
            self._alignment_offset_ra = solve.right_ascension - target_ra

            self.logger.info(
                f"Alignment offsets set to RA: {self._alignment_offset_ra} degrees, Dec: {self._alignment_offset_dec} degrees"
            )

            return True
        except Exception as e:
            self.logger.error(f"Error during alignment: {e}")
            return False

    def get_observation_strategy(self) -> ObservationStrategy:
        return ObservationStrategy.MANUAL

    def perform_observation_sequence(self, task_id, satellite_data) -> str:
        raise NotImplementedError
