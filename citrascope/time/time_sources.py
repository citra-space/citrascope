"""Time source implementations for CitraScope."""

import time
from abc import ABC, abstractmethod
from typing import Optional

import ntplib


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
