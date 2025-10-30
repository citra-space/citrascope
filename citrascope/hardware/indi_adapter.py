import os
import time

import PyIndi

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

    def __init__(self, CITRA_LOGGER, host: str, port: int):
        super(IndiAdapter, self).__init__()
        self.logger = CITRA_LOGGER
        self.logger.debug("creating an instance of IndiClient")
        self.host = host
        self.port = port

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

    def take_image(self, task_id: str):
        """Capture an image with the currently selected camera."""

        self._current_task_id = task_id
        ccd_exposure = self.our_camera.getNumber("CCD_EXPOSURE")
        ccd_exposure[0].setValue(1.0)
        self.sendNewNumber(ccd_exposure)

        time.sleep(1.0)  # this sleeping feels whack. Better to have a proper event system.
        while self.is_camera_busy() and self._current_task_id != "":
            self.logger.info("Waiting for camera to finish exposure...")
            time.sleep(2.0)

        filename = self._last_saved_filename
        self._last_saved_filename = ""
        return filename

    def is_camera_busy(self) -> bool:
        """Check if the camera is currently busy taking an image."""
        ccd_exposure = self.our_camera.getNumber("CCD_EXPOSURE")
        return ccd_exposure.getState() == PyIndi.IPS_BUSY
