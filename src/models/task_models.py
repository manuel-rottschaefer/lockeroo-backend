"""This module provides the Models for Station Maintenance events."""
# Types
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional
# Beanie
from beanie import Document, Link, Insert
from beanie import PydanticObjectId as ObjId
from beanie import SaveChanges, after_event, before_event
from pydantic import Field, PydanticUserError
from src.models.locker_models import LockerModel
# Models
from src.models.user_models import UserModel
from src.models.session_models import SessionModel, SessionState
from src.models.station_models import StationModel
# Services
from src.services.logging_services import logger_service as logger


class TaskState(str, Enum):
    """Possible states for Tasks."""
    QUEUED = "queued"
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELED = "canceled"


class TaskTarget(str, Enum):
    """Target of the queued actions."""
    USER = "user"           # Awaits user actions
    TERMINAL = "terminal"   # Awaits terminal actions
    LOCKER = "locker"       # Awaits locker actions


class TaskType(str, Enum):
    """Type of the queued actions."""
    REPORT = "report"
    CONFIRMATION = "confirmation"
    RESERVATION = "reservation"


class TaskItemModel(Document):  # pylint: disable=too-many-ancestors
    """Allows for both user and station tasks to be registered, queued
    at a station terminal and to register and handle timeout situations."""
    id: ObjId = Field(None, alias="_id")

    task_type: TaskType = Field(
        description="The type of action being queued/awaited.")

    target: TaskTarget = Field(
        description="The target of the action being queued/awaited.")

    assigned_user: Optional[Link[UserModel]] = Field(
        None, description="The user which this task handles.")

    assigned_session: Link[SessionModel] = Field(
        None, description="The session which this task handles.")

    assigned_station: Optional[Link[StationModel]] = Field(
        None, description="The station which this task may be assigned to.")

    assigned_locker: Optional[Link[LockerModel]] = Field(
        None, description="The station which this task may be assigned to.")

    task_state: TaskState = Field(
        TaskState.QUEUED,
        description='State of the task item. Not related to the session state.')

    queue_position: int = Field(
        0, description="The position of the task in the queue.")

    moves_session: bool = Field(
        False, description="Whether the session moves to the next state on task activation.")

    timeout_states: List[SessionState] = Field(
        default=[SessionState.EXPIRED],
        description="List of states the assigned session takes on after expiring, \
        each list item is a next try for this task.")

    from_expired: bool = Field(
        False, description="Whether the task is being requeued from an expired state.")

    expiration_window: float = Field(
        0, description="The time in seconds until the task expires.")

    created_at: Optional[datetime] = Field(
        None, description="The datetime when the task item was created.")

    expires_at: Optional[datetime] = Field(
        None, description="The timestamp when the task will time out.")

    activated_at: Optional[datetime] = Field(
        None, description="The datetime when the task item was activated.")

    completed_at: Optional[datetime] = Field(
        None, description="The datetime when the task item was completed or expired.")

    @ before_event(Insert)
    def handle_creation_event(self):
        self.created_at = datetime.now()

    @ after_event(Insert)
    async def log_creation(self):
        await self.fetch_link(TaskItemModel.assigned_session)
        logger.debug(
            (f"Created task '#{self.id}' of {self.task_type} "
             f"for session '#{self.assigned_session.id}'."))  # pylint: disable=no-member

    @ after_event(SaveChanges)
    async def log_state(self) -> None:
        """Log database operation."""
        if self.task_state != TaskState.QUEUED:
            logger.debug((f"Task '#{self.id}' for {self.target} of "
                          f"{self.task_type} set to {self.task_state}."))

    @ dataclass
    class Settings:
        name = "tasks"
        use_state_management = True

    @ dataclass
    class Config:
        json_schema_extra = {
            "_id": "5f7f9f8b0b7c0e001f6b0d0c",
            "task_type": "report",
            "target": "user",
            "task_state": "queued",
            "queue_position": 0,
            "moves_session": False,
            "timeout_states": ["expired"],
            "from_expired": False,
            "expiration_window": 0,
            "created_at": "2020-10-08T15:00:00",
            "expires_at": "2020-10-08T15:00:00",
            "activated_at": "2020-10-08T15:00:00",
            "completed_at": "2020-10-08T15:00:00"
        }


try:
    TaskItemModel.model_json_schema()
except PydanticUserError as exc_info:
    assert exc_info.code == 'invalid-for-json-schema'
