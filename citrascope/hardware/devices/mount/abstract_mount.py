"""Abstract mount device interface."""

from abc import abstractmethod
from typing import Optional, Tuple

from citrascope.hardware.devices.abstract_hardware_device import AbstractHardwareDevice


class AbstractMount(AbstractHardwareDevice):
    """Abstract base class for telescope mount devices.

    Provides a common interface for controlling equatorial and alt-az mounts.
    """

    @abstractmethod
    def slew_to_radec(self, ra: float, dec: float) -> bool:
        """Slew the mount to specified RA/Dec coordinates.

        Args:
            ra: Right Ascension in degrees
            dec: Declination in degrees

        Returns:
            True if slew initiated successfully, False otherwise
        """
        pass

    @abstractmethod
    def is_slewing(self) -> bool:
        """Check if mount is currently slewing.

        Returns:
            True if slewing, False if stationary or tracking
        """
        pass

    @abstractmethod
    def abort_slew(self):
        """Stop the current slew operation."""
        pass

    @abstractmethod
    def get_radec(self) -> Tuple[float, float]:
        """Get current mount RA/Dec position.

        Returns:
            Tuple of (RA in degrees, Dec in degrees)
        """
        pass

    @abstractmethod
    def start_tracking(self, rate: Optional[str] = "sidereal") -> bool:
        """Start tracking at specified rate.

        Args:
            rate: Tracking rate - "sidereal", "lunar", "solar", or device-specific

        Returns:
            True if tracking started successfully, False otherwise
        """
        pass

    @abstractmethod
    def stop_tracking(self) -> bool:
        """Stop tracking.

        Returns:
            True if tracking stopped successfully, False otherwise
        """
        pass

    @abstractmethod
    def is_tracking(self) -> bool:
        """Check if mount is currently tracking.

        Returns:
            True if tracking, False otherwise
        """
        pass

    @abstractmethod
    def park(self) -> bool:
        """Park the mount to its home position.

        Returns:
            True if park initiated successfully, False otherwise
        """
        pass

    @abstractmethod
    def unpark(self) -> bool:
        """Unpark the mount from its home position.

        Returns:
            True if unpark successful, False otherwise
        """
        pass

    @abstractmethod
    def is_parked(self) -> bool:
        """Check if mount is parked.

        Returns:
            True if parked, False otherwise
        """
        pass

    @abstractmethod
    def get_mount_info(self) -> dict:
        """Get mount capabilities and information.

        Returns:
            Dictionary containing mount specs and capabilities
        """
        pass
