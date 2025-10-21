from abc import ABC, abstractmethod


class AstroHardwareAdapter(ABC):
    """
    Abstract base class for controlling astrophotography hardware.

    This adapter provides a common interface for interacting with telescopes, cameras,
    filter wheels, focus dials, and other astrophotography devices.
    """

    @abstractmethod
    def connect(self, host: str, port: int) -> bool:
        """Connect to the hardware server."""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the hardware server."""
        pass

    @abstractmethod
    def list_devices(self) -> list[str]:
        """List all connected devices."""
        pass

    @abstractmethod
    def select_camera(self, device_name: str) -> bool:
        """Select a specific camera by name."""
        pass

    @abstractmethod
    def point_telescope(self, ra: float, dec: float):
        """Point the telescope to the specified RA/Dec coordinates."""
        pass

    @abstractmethod
    def get_telescope_direction(self) -> tuple[float, float]:
        """Read the current telescope direction (RA, Dec)."""
        pass

    @abstractmethod
    def telescope_is_moving(self) -> bool:
        """Check if the telescope is currently moving."""
        pass
