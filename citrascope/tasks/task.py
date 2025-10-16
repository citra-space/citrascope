from dataclasses import dataclass


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
        )

    def __repr__(self):
        return f"<Task {self.id} {self.type} {self.status}>"
