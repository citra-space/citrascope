"""GPS monitoring for CitraScope.

Monitors GPS receiver via gpsd/gpspipe to provide location and fix quality information.
"""

import json
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from citrascope.logging import CITRASCOPE_LOGGER


@dataclass
class GPSFix:
    """GPS fix information."""

    latitude: Optional[float] = None  # degrees
    longitude: Optional[float] = None  # degrees
    altitude: Optional[float] = None  # meters
    fix_mode: int = 0  # 0=no fix, 2=2D, 3=3D
    satellites: int = 0  # number of satellites used
    timestamp: float = 0.0  # time.time() when fix was obtained

    @property
    def is_strong_fix(self) -> bool:
        """Check if this is a strong GPS fix (3D with 4+ satellites)."""
        return self.fix_mode >= 3 and self.satellites >= 4


class GPSMonitor:
    """
    Background thread that monitors GPS receiver via gpsd.

    Periodically queries gpsd using gpspipe to get location and fix quality.
    Provides thread-safe access to latest GPS fix and optional callback
    when fix quality changes.
    """

    def __init__(
        self,
        check_interval_minutes: int = 5,
        fix_callback: Optional[Callable[[GPSFix], None]] = None,
    ):
        """
        Initialize GPS monitor.

        Args:
            check_interval_minutes: Minutes between GPS checks
            fix_callback: Optional callback function called with GPSFix when fix quality changes
        """
        self.check_interval_minutes = check_interval_minutes
        self.fix_callback = fix_callback

        # Thread control
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Current fix status
        self._current_fix: Optional[GPSFix] = None
        self._last_fix_mode = 0

    def is_available(self) -> bool:
        """
        Check if GPS is available (gpspipe command exists).

        Returns:
            True if gpspipe command is available, False otherwise.
        """
        try:
            result = subprocess.run(
                ["which", "gpspipe"],
                capture_output=True,
                timeout=2,
            )
            return result.returncode == 0
        except Exception:
            return False

    def start(self) -> None:
        """Start the GPS monitoring thread."""
        if self._thread is not None and self._thread.is_alive():
            CITRASCOPE_LOGGER.warning("GPS monitor already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        CITRASCOPE_LOGGER.info(f"GPS monitor started (check interval: {self.check_interval_minutes} minutes)")

    def stop(self) -> None:
        """Stop the GPS monitoring thread."""
        if self._thread is None:
            return

        CITRASCOPE_LOGGER.info("Stopping GPS monitor...")
        self._stop_event.set()
        self._thread.join(timeout=5.0)
        self._thread = None
        CITRASCOPE_LOGGER.info("GPS monitor stopped")

    def get_current_fix(self) -> Optional[GPSFix]:
        """Get the current GPS fix (thread-safe)."""
        with self._lock:
            return self._current_fix

    def _monitor_loop(self) -> None:
        """Main monitoring loop (runs in background thread)."""
        # Perform initial check immediately
        self._check_gps()

        # Then check periodically
        interval_seconds = self.check_interval_minutes * 60

        while not self._stop_event.is_set():
            # Wait for interval or stop signal
            if self._stop_event.wait(timeout=interval_seconds):
                break

            self._check_gps()

    def _check_gps(self) -> None:
        """Perform a single GPS check."""
        try:
            fix = self._query_gpsd()

            # Store current fix (thread-safe)
            with self._lock:
                self._current_fix = fix

            # Log based on fix quality
            if fix:
                self._log_fix_status(fix)

                # Notify callback if fix quality changed
                if self.fix_callback and fix.fix_mode != self._last_fix_mode:
                    self._last_fix_mode = fix.fix_mode
                    try:
                        self.fix_callback(fix)
                    except Exception as e:
                        CITRASCOPE_LOGGER.error(f"GPS fix callback failed: {e}", exc_info=True)
            else:
                CITRASCOPE_LOGGER.warning("GPS fix unavailable")
                self._last_fix_mode = 0

        except Exception as e:
            CITRASCOPE_LOGGER.error(f"GPS check failed: {e}", exc_info=True)
            with self._lock:
                self._current_fix = None

    def _query_gpsd(self) -> Optional[GPSFix]:
        """
        Query gpsd for GPS fix information using gpspipe.

        Returns:
            GPSFix object with location and fix quality, or None if unavailable.
        """
        try:
            # Use gpspipe to get JSON output from gpsd
            # Request 10 messages to ensure we get both TPV (position) and SKY (satellites)
            result = subprocess.run(
                ["gpspipe", "-w", "-n", "10"],
                capture_output=True,
                timeout=5,
                text=True,
            )

            if result.returncode != 0:
                return None

            # Parse JSON lines to extract data
            fix = GPSFix(timestamp=time.time())

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    msg_class = data.get("class")

                    # Extract position and fix mode from TPV message
                    if msg_class == "TPV":
                        if "mode" in data:
                            fix.fix_mode = data["mode"]
                        if "lat" in data:
                            fix.latitude = data["lat"]
                        if "lon" in data:
                            fix.longitude = data["lon"]
                        if "alt" in data:
                            fix.altitude = data["alt"]

                    # Extract satellite count from SKY message
                    if msg_class == "SKY":
                        # Prefer uSat (used satellites) if available
                        if "uSat" in data:
                            fix.satellites = data["uSat"]
                        # Fall back to counting satellites array
                        elif "satellites" in data:
                            fix.satellites = len([s for s in data["satellites"] if s.get("used", False)])

                except json.JSONDecodeError:
                    continue

            # Only return fix if we got at least position data
            if fix.latitude is not None and fix.longitude is not None:
                return fix
            else:
                return None

        except (FileNotFoundError, OSError):
            # gpspipe not available or gpsd not running
            return None
        except Exception as e:
            CITRASCOPE_LOGGER.debug(f"Could not query gpsd: {e}")
            return None

    def _log_fix_status(self, fix: GPSFix) -> None:
        """Log GPS fix status at appropriate level."""
        if fix.latitude is None or fix.longitude is None:
            CITRASCOPE_LOGGER.warning("GPS position unavailable")
            return

        fix_type = ["no fix", "no fix", "2D", "3D"][min(fix.fix_mode, 3)]
        location_str = f"lat={fix.latitude:.6f}°, lon={fix.longitude:.6f}°"
        if fix.altitude is not None:
            location_str += f", alt={fix.altitude:.1f}m"

        if fix.is_strong_fix:
            CITRASCOPE_LOGGER.info(f"GPS strong fix: {location_str} ({fix.satellites} sats, {fix_type})")
        elif fix.fix_mode >= 2:
            CITRASCOPE_LOGGER.info(f"GPS weak fix: {location_str} ({fix.satellites} sats, {fix_type})")
        else:
            CITRASCOPE_LOGGER.warning(f"GPS no fix: {fix.satellites} sats")
