"""Location service for CitraScope.

Manages ground station location from GPS or API sources with intelligent fallback.
"""

import threading
import time
from typing import TYPE_CHECKING, Optional

from citrascope.location.gps_monitor import GPSMonitor
from citrascope.logging import CITRASCOPE_LOGGER

if TYPE_CHECKING:
    from citrascope.api.abstract_api_client import AbstractCitraApiClient
    from citrascope.location.gps_monitor import GPSFix
    from citrascope.settings.citrascope_settings import CitraScopeSettings


class LocationService:
    """
    Location service that coordinates GPS updates and provides current location.

    Architecture note: Ground stations have locations (lat/long/alt), not telescopes.
    Telescopes are physically located AT ground stations. For mobile ground stations
    with GPS, location updates dynamically. For fixed ground stations, location is
    static configuration.

    The service manages GPS monitoring internally, starting it if available and
    handling all GPS lifecycle operations.
    """

    # GPS polling interval - how often to check GPS for fresh coordinates
    GPS_CHECK_INTERVAL_SECONDS = 10

    # Maximum age for GPS fix before falling back to ground station (5 minutes)
    GPS_MAX_AGE_SECONDS = 300

    def __init__(
        self,
        api_client: Optional["AbstractCitraApiClient"] = None,
        settings: Optional["CitraScopeSettings"] = None,
    ):
        """
        Initialize location service with GPS monitoring.

        Args:
            api_client: API client for updating ground station location
            settings: Settings object for configuration
        """
        self.api_client = api_client
        self.settings = settings
        self._ground_station_ref: Optional[dict] = None
        self._lock = threading.Lock()  # Protect _ground_station_ref access
        self._last_server_update = 0.0  # Track last server update for rate limiting

        # Initialize GPS monitor with frequent polling (for UI freshness)
        # Server updates are rate-limited in the callback to gps_update_interval_minutes
        self.gps_monitor = GPSMonitor(
            check_interval_minutes=self.GPS_CHECK_INTERVAL_SECONDS / 60,
            fix_callback=self.on_gps_fix_changed,
        )

        if self.gps_monitor.is_available():
            self.gps_monitor.start()
            CITRASCOPE_LOGGER.info("GPS monitoring started by location service")
        else:
            CITRASCOPE_LOGGER.info("GPS not available - location service using API-only mode")
            self.gps_monitor = None

    def stop(self) -> None:
        """Stop GPS monitoring."""
        if self.gps_monitor:
            self.gps_monitor.stop()
            self.gps_monitor = None

    def set_ground_station(self, ground_station: dict) -> None:
        """
        Set the ground station record reference from API.

        Args:
            ground_station: Ground station record from API (will be kept as reference)
        """
        with self._lock:
            self._ground_station_ref = ground_station

    def on_gps_fix_changed(self, fix: "GPSFix") -> None:
        """
        Callback invoked when GPS fix is checked by background thread (every 10 seconds).

        Updates ground station location on Citra API when strong fix is available,
        but rate-limited to gps_update_interval_minutes to avoid API spam.

        Args:
            fix: Current GPS fix information
        """
        # Check if GPS location updates are enabled
        if not self.settings or not self.settings.gps_location_updates_enabled:
            return

        # Validate fix quality and coordinate data
        if not fix.is_strong_fix:
            return

        # Additional validation: is_strong_fix now guarantees these are not None,
        # but be explicit for type checker and future-proofing
        if fix.latitude is None or fix.longitude is None or fix.altitude is None:
            CITRASCOPE_LOGGER.warning("GPS fix missing coordinate data despite strong fix status")
            return

        # Rate limit server updates (GPS polled every 10s, but only update server every N minutes)
        current_time = time.time()
        update_interval_seconds = self.settings.gps_update_interval_minutes * 60
        if current_time - self._last_server_update < update_interval_seconds:
            # Too soon - skip this update
            return

        # Thread-safe access to ground station reference
        with self._lock:
            if self.api_client and self._ground_station_ref:
                ground_station_id = self._ground_station_ref["id"]
                result = self.api_client.update_ground_station_location(
                    ground_station_id,
                    fix.latitude,
                    fix.longitude,
                    fix.altitude,
                )
                if result:
                    # Keep local cache in sync with server (atomic update within lock)
                    self._ground_station_ref["latitude"] = fix.latitude
                    self._ground_station_ref["longitude"] = fix.longitude
                    self._ground_station_ref["altitude"] = fix.altitude

                    # Update timestamp after successful server update
                    self._last_server_update = current_time

                    CITRASCOPE_LOGGER.info(
                        f"Updated ground station location from GPS: "
                        f"lat={fix.latitude:.6f}, lon={fix.longitude:.6f}, alt={fix.altitude:.1f}m"
                    )

    def get_current_location(self) -> Optional[dict]:
        """
        Location service - returns best available location.

        Priority:
        1. GPS (if enabled, strong fix, and fresh data) - live location for mobile stations
        2. Ground station (from API) - configured fallback for fixed stations

        Returns:
            Dictionary with latitude, longitude, altitude, and source, or None if unavailable.
        """
        # Try GPS first if available and GPS location updates are enabled
        if self.gps_monitor and self.settings and self.settings.gps_location_updates_enabled:
            fix = self.gps_monitor.get_current_fix()
            if fix and fix.is_strong_fix:
                # Check if GPS data is fresh (not stale)
                age_seconds = time.time() - fix.timestamp
                if age_seconds < self.GPS_MAX_AGE_SECONDS:
                    return {
                        "latitude": fix.latitude,
                        "longitude": fix.longitude,
                        "altitude": fix.altitude,
                        "source": "gps",
                    }
                else:
                    CITRASCOPE_LOGGER.warning(
                        f"GPS fix is stale ({age_seconds:.0f}s old), falling back to ground station location"
                    )

        # Fall back to ground station location (thread-safe read)
        with self._lock:
            if self._ground_station_ref:
                return {
                    "latitude": self._ground_station_ref["latitude"],
                    "longitude": self._ground_station_ref["longitude"],
                    "altitude": self._ground_station_ref["altitude"],
                    "source": "ground_station",
                }

        return None
