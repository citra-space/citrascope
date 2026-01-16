from dataclasses import dataclass
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
            assigned_filter_name=data.get("assigned_filter_name"),
        )

    def __repr__(self):
        return f"<Task {self.id} {self.type} {self.status}>"
