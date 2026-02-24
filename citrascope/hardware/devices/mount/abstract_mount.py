"""Abstract mount device interface."""

from abc import abstractmethod

from citrascope.hardware.devices.abstract_hardware_device import AbstractHardwareDevice


class AbstractMount(AbstractHardwareDevice):
    """Abstract base class for telescope mount devices.

    Provides a common interface for controlling equatorial and alt-az mounts.
    All RA/Dec coordinates are in **degrees** (project convention).
    """

    # ------------------------------------------------------------------
    # Core abstract methods — every mount must implement these
    # ------------------------------------------------------------------

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
    def get_radec(self) -> tuple[float, float]:
        """Get current mount RA/Dec position.

        Returns:
            Tuple of (RA in degrees, Dec in degrees)
        """
        pass

    @abstractmethod
    def start_tracking(self, rate: str | None = "sidereal") -> bool:
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

    # ------------------------------------------------------------------
    # Optional capability methods — concrete defaults so subclasses only
    # override what they support.
    # ------------------------------------------------------------------

    def sync_to_radec(self, ra: float, dec: float) -> bool:
        """Sync the mount's internal model to the given coordinates.

        Tells the mount that it is currently pointing at (ra, dec).
        Used after plate-solving to correct pointing errors.

        Args:
            ra: Right Ascension in degrees
            dec: Declination in degrees

        Returns:
            True if sync accepted, False otherwise
        """
        raise NotImplementedError(f"{type(self).__name__} does not support sync")

    def set_custom_tracking_rates(self, ra_rate: float, dec_rate: float) -> bool:
        """Set custom tracking rates for satellite or non-sidereal tracking.

        Args:
            ra_rate: RA tracking rate offset in arcseconds per second
            dec_rate: Dec tracking rate offset in arcseconds per second

        Returns:
            True if rates accepted, False if unsupported
        """
        return False

    def guide_pulse(self, direction: str, duration_ms: int) -> bool:
        """Send an autoguiding correction pulse.

        Args:
            direction: One of "north", "south", "east", "west"
            duration_ms: Pulse duration in milliseconds (typically 0-9999)

        Returns:
            True if pulse sent, False if unsupported
        """
        return False

    def set_site_location(self, latitude: float, longitude: float, altitude: float) -> bool:
        """Set the observing site location on the mount.

        Args:
            latitude: Latitude in decimal degrees (positive = North)
            longitude: Longitude in decimal degrees (positive = East)
            altitude: Altitude in metres above sea level

        Returns:
            True if accepted, False if unsupported
        """
        return False

    def get_site_location(self) -> tuple[float, float, float] | None:
        """Get the observing site location stored on the mount.

        Returns:
            (latitude, longitude, altitude) or None if unsupported
        """
        return None

    def sync_datetime(self) -> bool:
        """Sync the system clock to the mount's internal clock.

        Pushes the current UTC date/time so the mount can compute
        sidereal time, horizon limits, and meridian flips.

        Returns:
            True if accepted, False if unsupported
        """
        return False
