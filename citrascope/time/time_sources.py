"""Time source implementations for CitraScope."""

import subprocess
import time
from abc import ABC, abstractmethod
from typing import Optional

import ntplib

from citrascope.logging import CITRASCOPE_LOGGER


class AbstractTimeSource(ABC):
    """Abstract base class for time sources."""

    @abstractmethod
    def get_offset_ms(self) -> Optional[float]:
        """
        Get the clock offset in milliseconds.

        Returns:
            Clock offset in milliseconds (positive = system ahead), or None if unavailable.
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Get the name of this time source."""
        pass

    def get_metadata(self) -> Optional[dict]:
        """
        Get optional metadata about the time source.

        Returns:
            Dictionary with metadata, or None if not applicable.
        """
        return None


class NTPTimeSource(AbstractTimeSource):
    """NTP-based time source using pool.ntp.org."""

    def __init__(self, ntp_server: str = "pool.ntp.org", timeout: int = 5):
        """
        Initialize NTP time source.

        Args:
            ntp_server: NTP server hostname (default: pool.ntp.org)
            timeout: Query timeout in seconds
        """
        self.ntp_server = ntp_server
        self.timeout = timeout
        self.client = ntplib.NTPClient()

    def get_offset_ms(self) -> Optional[float]:
        """
        Query NTP server for clock offset.

        Returns:
            Clock offset in milliseconds, or None if query fails.
        """
        try:
            response = self.client.request(self.ntp_server, version=3, timeout=self.timeout)
            # NTP offset is in seconds, convert to milliseconds
            offset_ms = response.offset * 1000.0
            return offset_ms
        except Exception:
            # Query failed - network issue, timeout, etc.
            return None

    def get_source_name(self) -> str:
        """Get the name of this time source."""
        return "ntp"


def _get_gpsd_metadata() -> Optional[dict]:
    """
    Query gpsd for satellite count and fix quality.

    Returns:
        Dictionary with 'satellites' and 'fix_mode' keys, or None if unavailable.
    """
    try:
        import socket
        import json

        # Connect directly to gpsd and send POLL command
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("localhost", 2947))
        sock.settimeout(5.0)
        stream = sock.makefile(mode="rw")

        # Read welcome message
        stream.readline()

        # Enable watch
        stream.write('?WATCH={"enable":true}\n')
        stream.flush()

        # Read watch responses
        for _ in range(2):
            stream.readline()

        # Poll for current data
        stream.write("?POLL;\n")
        stream.flush()
        response = json.loads(stream.readline())

        sock.close()

        # Extract fix mode from TPV data
        fix_mode = 0
        if "tpv" in response and response["tpv"]:
            fix_mode = response["tpv"][-1].get("mode", 0)

        # Extract satellite count from SKY data
        satellites = 0
        if "sky" in response and response["sky"]:
            last_sky = response["sky"][-1]
            # Try satellites array first (most detailed)
            if "satellites" in last_sky:
                sats_list = last_sky["satellites"]
                satellites = len([s for s in sats_list if s.get("used", False)])
            # Fall back to uSat field (used satellites count)
            elif "uSat" in last_sky:
                satellites = last_sky["uSat"]

        return {"satellites": satellites, "fix_mode": fix_mode}
    except Exception:
        return None


class ChronyTimeSource(AbstractTimeSource):
    """Chrony-based time source that detects GPS references."""

    def __init__(self, timeout: int = 5):
        """
        Initialize Chrony time source.

        Args:
            timeout: Command timeout in seconds
        """
        self.timeout = timeout
        self._gps_metadata: Optional[dict] = None
        self._source_name: str = "chrony"

    def is_available(self) -> bool:
        """
        Check if chrony is available and running.

        Returns:
            True if chronyc command succeeds, False otherwise.
        """
        try:
            result = subprocess.run(
                ["chronyc", "-c", "tracking"],
                capture_output=True,
                timeout=self.timeout,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_offset_ms(self) -> Optional[float]:
        """
        Query chrony for clock offset and detect GPS reference.

        Returns:
            Clock offset in milliseconds, or None if query fails.
        """
        try:
            # Get tracking info for offset
            tracking_result = subprocess.run(
                ["chronyc", "-c", "tracking"],
                capture_output=True,
                timeout=self.timeout,
                text=True,
                check=True,
            )

            # Parse CSV output: field index 4 is "System time" in seconds
            tracking_fields = tracking_result.stdout.strip().split(",")
            if len(tracking_fields) > 4:
                offset_seconds = float(tracking_fields[4])
                offset_ms = offset_seconds * 1000.0
            else:
                return None

            # Get sources to detect GPS reference
            sources_result = subprocess.run(
                ["chronyc", "-c", "sources"],
                capture_output=True,
                timeout=self.timeout,
                text=True,
                check=True,
            )

            # Parse sources to detect GPS
            gps_detected = False
            for line in sources_result.stdout.strip().split("\n"):
                if not line:
                    continue

                fields = line.split(",")
                if len(fields) < 3:
                    continue

                mode = fields[0]  # '#' = local reference
                state = fields[1]  # '*' = currently selected
                name = fields[2].upper()

                # Check if this is a selected GPS reference
                if "*" in state and "#" in mode:
                    # Check for GPS-related names
                    gps_keywords = ["GPS", "SHM", "PPS", "SOCK", "NMEA"]
                    if any(keyword in name for keyword in gps_keywords):
                        gps_detected = True
                        break

            # If GPS detected, query gpsd for metadata
            if gps_detected:
                self._source_name = "gps"
                CITRASCOPE_LOGGER.info("GPS reference detected in chrony sources")
                self._gps_metadata = _get_gpsd_metadata()
                if self._gps_metadata:
                    CITRASCOPE_LOGGER.info(
                        f"GPS lock acquired: {self._gps_metadata['satellites']} satellites, "
                        f"fix mode {self._gps_metadata['fix_mode']}"
                    )
                else:
                    CITRASCOPE_LOGGER.warning(
                        "GPS reference active in chrony but gpsd metadata unavailable "
                        "(gpsd may not be running or GPS library not installed)"
                    )
            else:
                self._source_name = "chrony"
                self._gps_metadata = None
                CITRASCOPE_LOGGER.warning("No GPS reference detected in chrony sources - using NTP/other time source")

            return offset_ms

        except Exception:
            return None

    def get_source_name(self) -> str:
        """Get the name of this time source."""
        return self._source_name

    def get_metadata(self) -> Optional[dict]:
        """
        Get GPS metadata if available.

        Returns:
            Dictionary with GPS metadata, or None.
        """
        return self._gps_metadata
