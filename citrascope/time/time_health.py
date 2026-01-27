"""Time health status calculation and monitoring."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TimeStatus(str, Enum):
    """Time synchronization status levels."""

    OK = "ok"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class TimeHealth:
    """Time synchronization health status."""

    offset_ms: Optional[float]
    """Clock offset in milliseconds (positive = system clock ahead)."""

    status: TimeStatus
    """Current time sync status level."""

    source: str
    """Time source used (ntp, unknown)."""

    message: Optional[str] = None
    """Optional status message or error description."""

    @staticmethod
    def calculate_status(
        offset_ms: Optional[float],
        pause_threshold: float,
    ) -> TimeStatus:
        """
        Calculate time status based on offset and pause threshold.

        Args:
            offset_ms: Clock offset in milliseconds (None if check failed)
            pause_threshold: Threshold in milliseconds that triggers task pause

        Returns:
            TimeStatus level (OK, CRITICAL, or UNKNOWN)
        """
        if offset_ms is None:
            return TimeStatus.UNKNOWN

        abs_offset = abs(offset_ms)

        if abs_offset < pause_threshold:
            return TimeStatus.OK
        else:
            return TimeStatus.CRITICAL

    @classmethod
    def from_offset(
        cls,
        offset_ms: Optional[float],
        source: str,
        pause_threshold: float,
        message: Optional[str] = None,
    ) -> "TimeHealth":
        """
        Create TimeHealth from offset and pause threshold.

        Args:
            offset_ms: Clock offset in milliseconds
            source: Time source identifier
            pause_threshold: Threshold that triggers task pause
            message: Optional status message

        Returns:
            TimeHealth instance
        """
        status = cls.calculate_status(offset_ms, pause_threshold)
        return cls(
            offset_ms=offset_ms,
            status=status,
            source=source,
            message=message,
        )

    def is_safe_for_observations(self) -> bool:
        """Check if time sync is acceptable for astronomical observations."""
        return self.status == TimeStatus.OK

    def requires_critical_action(self) -> bool:
        """Check if critical action is required (pause observations)."""
        return self.status == TimeStatus.CRITICAL

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "offset_ms": self.offset_ms,
            "status": self.status.value,
            "source": self.source,
            "message": self.message,
        }
