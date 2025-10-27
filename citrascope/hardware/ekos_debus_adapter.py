import asyncio

import PyIndi
from dbus_fast import BusType
from dbus_fast.aio import MessageBus

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter

# dbus_fast docs: https://dbus-fast.readthedocs.io/en/latest/high-level-client/index.html


class EkosDbusAdapter(PyIndi.BaseClient, AbstractAstroHardwareAdapter):
    def __init__(self, CITRA_LOGGER):
        super(EkosDbusAdapter, self).__init__()
        self.logger = CITRA_LOGGER
        self.logger.debug("creating an instance of EkosDbusAdapter")

    def connect(self) -> bool:
        """Connect to the hardware server."""
        bus = asyncio.run(MessageBus(bus_type=BusType.SESSION).connect())  # correct buss type?
        introspection = asyncio.run(bus.introspect("org.kde.kstars", "/KStars/Ekos"))
        self.logger.debug(f"Ekos Introspection data: {introspection}")

    def disconnect(self):
        """Disconnect from the hardware server."""
        pass

    def list_devices(self) -> list[str]:
        """List all connected devices."""
        pass

    def select_telescope(self, device_name: str) -> bool:
        """Select a specific camera by name."""
        pass

    def point_telescope(self, ra: float, dec: float):
        """Point the telescope to the specified RA/Dec coordinates."""
        pass

    def get_telescope_direction(self) -> tuple[float, float]:
        """Read the current telescope direction (RA, Dec)."""
        pass

    def telescope_is_moving(self) -> bool:
        """Check if the telescope is currently moving."""
        pass

    def select_camera(self, device_name: str) -> bool:
        """Select a specific camera by name."""
        pass

    def take_image(self, task_id: str) -> str:
        """Capture an image with the currently selected camera. Returns the file path of the saved image."""
        pass
