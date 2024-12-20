"""This module provides the Models for Station Maintenance events."""
# Types
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional, Union

# Beanie
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import SaveChanges, after_event
from dotenv import load_dotenv
from pydantic import Field

# Models
from src.models.session_models import SessionModel, SessionStates
from src.models.station_models import StationModel
from src.models.locker_models import LockerModel, LockerStates

# Services
from src.services.logging_services import logger


load_dotenv('environments/.env')


class TaskStates(str, Enum):
    """Possible states for Tasks."""
    QUEUED = "queued"               # Session is queued for verification/payment
    PENDING = "pending"             # Session is awaiting verification/payment
    COMPLETED = "completed"         # Session has been verified/paid
    EXPIRED = "expired"             # Session has expired


class TaskTarget(str, Enum):
    """Target of the queued actions."""
    USER = "user"  # Awaits user actions
    TERMINAL = "terminal"  # Awaits terminal actions
    LOCKER = "locker"  # Awaits locker actions


class TaskType(str, Enum):
    """Type of the queued actions."""
    REPORT = "report"  # Awaits an action report
    CONFIRMATION = "confirmation"  # Awaits an action confirmation


class TaskItemModel(Document):  # pylint: disable=too-many-ancestors
    """Allows for both user and station tasks to be registered, queued
    at a station terminal and to register and handle timeout situations."""
    id: ObjId = Field(None, alias="_id")

    task_type: TaskType = Field(
        description="The type of action being queued/awaited.")

    target: TaskTarget = Field(
        description="The target of the action being queued/awaited.")

    assigned_session: Link[SessionModel] = Field(
        None, description="The session which this task handles.")

    assigned_station: Optional[Link[StationModel]] = Field(
        None, description="The station which this task may be assigned to.")

    assigned_locker: Optional[Link[LockerModel]] = Field(
        None, description="The station which this task may be assigned to.")

    task_state: TaskStates = Field(
        TaskStates.QUEUED,
        description='State of the task item. Not related to the session state.')

    queued_session_state: Optional[Union[LockerStates, SessionStates]] = Field(
        None,
        description="The next state of the assigned session or terminal after activation.\
        State Type depends on task type.")

    timeout_states: List[SessionStates] = Field(
        default=[SessionStates.EXPIRED],
        description="List of states the assigned session takes on after expiring, \
        each list item is a next try for this task.")

    expiration_window: int = Field(
        0, description="The time in seconds until the task expires.")

    expires_at: Optional[datetime] = Field(
        None, description="The timestamp when the task will time out.")

    created_ts: datetime = Field(
        datetime.now(),
        description="The datetime when the task item was created.")

    activated_at: Optional[datetime] = Field(
        None, description="The datetime when the task item was activated.")

    completed_at: Optional[datetime] = Field(
        None, description="The datetime when the task item was completed or expired.")

    @after_event(SaveChanges)
    async def log_state(self) -> None:
        """Log database operation."""
        logger.debug(f"Task '#{self.id}' for {self.target} of {
                     self.task_type} set to {self.task_state}.")

    @dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "tasks"
        use_state_management = True
