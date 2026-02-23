import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    id: str
    type: str
    status: str
    creationEpoch: str
    updateEpoch: str
    taskStart: str
    taskStop: str
    userId: str
    username: str
    satelliteId: str
    satelliteName: str
    telescopeId: str
    telescopeName: str
    groundStationId: str
    groundStationName: str
    assigned_filter_name: Optional[str] = None

    # Local execution state (not from API, never sent to server)
    local_status_msg: Optional[str] = None
    retry_scheduled_time: Optional[float] = None  # Unix timestamp when retry will execute (None if not retrying)
    is_being_executed: bool = False  # True when a worker is actively executing this task

    # Thread safety for status fields (not included in __init__)
    _status_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            id=data.get("id"),
            type=data.get("type", ""),
            status=data.get("status"),
            creationEpoch=data.get("creationEpoch", ""),
            updateEpoch=data.get("updateEpoch", ""),
            taskStart=data.get("taskStart", ""),
            taskStop=data.get("taskStop", ""),
            userId=data.get("userId", ""),
            username=data.get("username", ""),
            satelliteId=data.get("satelliteId", ""),
            satelliteName=data.get("satelliteName", ""),
            telescopeId=data.get("telescopeId", ""),
            telescopeName=data.get("telescopeName", ""),
            groundStationId=data.get("groundStationId", ""),
            groundStationName=data.get("groundStationName", ""),
            assigned_filter_name=data.get("assignedFilterName"),
        )

    def set_status_msg(self, msg: Optional[str]):
        """Thread-safe setter for local_status_msg."""
        with self._status_lock:
            self.local_status_msg = msg

    def get_status_msg(self) -> Optional[str]:
        """Thread-safe getter for local_status_msg."""
        with self._status_lock:
            return self.local_status_msg

    def set_retry_time(self, timestamp: Optional[float]):
        """Thread-safe setter for retry_scheduled_time."""
        with self._status_lock:
            self.retry_scheduled_time = timestamp

    def get_retry_time(self) -> Optional[float]:
        """Thread-safe getter for retry_scheduled_time."""
        with self._status_lock:
            return self.retry_scheduled_time

    def set_executing(self, executing: bool):
        """Thread-safe setter for is_being_executed."""
        with self._status_lock:
            self.is_being_executed = executing

    def get_executing(self) -> bool:
        """Thread-safe getter for is_being_executed."""
        with self._status_lock:
            return self.is_being_executed

    def get_status_info(self) -> tuple[Optional[str], Optional[float], bool]:
        """Thread-safe getter for all status fields at once."""
        with self._status_lock:
            return (self.local_status_msg, self.retry_scheduled_time, self.is_being_executed)

    def __repr__(self):
        return f"<Task {self.id} {self.type} {self.status}>"
