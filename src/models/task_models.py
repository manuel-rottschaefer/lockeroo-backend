"""This module provides the Models for Station Maintenance events."""
# Types
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional, Union

# Beanie
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import Update, after_event
from dotenv import load_dotenv
from pydantic import Field

from src.models.locker_models import LockerStates
# Models
from src.models.session_models import SessionModel, SessionStates
from src.models.station_models import StationModel
from src.models.locker_models import LockerStates

# Services
from src.services.logging_services import logger


load_dotenv('src/environments/.env')


class TaskStates(str, Enum):
    """Possible states for Tasks."""
    QUEUED = "queued"               # Session is queued for verification/payment
    PENDING = "pending"             # Session is awaiting verification/payment
    COMPLETED = "completed"         # Session has been verified/paid
    EXPIRED = "expired"             # Session has expired


class TaskTypes(str, Enum):
    """Types of queued actions."""
    USER = "user"                   # Awaiting action of user (verification/payment)
    TERMINAL = "terminal"           # Awaiting station to confirm terminal state
    LOCKER = "locker"               # Awaiting station to confirm locker state


class TaskItemModel(Document):  # pylint: disable=too-many-ancestors
    """Allows for both user and station tasks to be registered, queued
    at a station terminal and to register and handle timeout situations."""
    id: ObjId = Field(None, alias="_id")

    task_type: TaskTypes = Field(
        TaskTypes.USER, description="The type of action being queued/awaited.")

    assigned_session: Link[SessionModel] = Field(
        None, description="The session which this task handles.")

    assigned_station: Link[StationModel] = Field(
        None, description="The station assigned to the related session.")

    task_state: TaskStates = Field(
        TaskStates.QUEUED,
        description='State of the task item. Not related to the session state.')

    queue_enabled: bool = Field(
        False, description="The task can be put into a queue at its\
        assigned station or be immediately activated.")

    queued_state: Optional[Union[LockerStates, SessionStates]] = Field(
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

    completed: Optional[datetime] = Field(
        None, description="The datetime when the task item was completed or expired.")

    @after_event(Update)
    async def log_state(self) -> None:
        """Log database operation."""
        await self.sync()
        logger.debug(f"Task '{self.id}' of type {
                     self.task_type} set to {self.task_state}.")

    @dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "tasks"
