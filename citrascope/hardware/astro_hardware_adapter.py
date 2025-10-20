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
    def list_devices(self):
        """List all connected devices."""
        pass

    @abstractmethod
    def select_device(self, device_name: str) -> bool:
        """Select a specific device by name."""
        pass

    @abstractmethod
    def update_device_property(self, device_name: str, property_name: str, value):
        """Update a property of a specific device."""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the hardware server."""
        pass
