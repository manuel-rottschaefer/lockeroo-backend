"""Models for queue items."""

# Types
import os
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List
from dotenv import load_dotenv
from pydantic import Field

# Beanie
from beanie import Document, Link, Update, after_event
from beanie import PydanticObjectId as ObjId

# Models
from src.models.session_models import SessionModel, SessionStates
from src.models.station_models import StationModel

# Logging
from src.services.logging_services import logger

load_dotenv('src/environments/.env')


class QueueStates(str, Enum):
    """States for a terminal queue."""
    QUEUED = "queued"               # Session is queued for verification/payment
    PENDING = "pending"             # Session is awaiting verification/payment
    COMPLETED = "completed"         # Session has been verified/paid
    EXPIRED = "expired"             # Session has expired


class QueueTypes(str, Enum):
    """Types of queued actions."""
    USER = "user"
    STATION = "station"


EXPIRATION_DURATIONS: Dict[SessionStates, int] = {
    SessionStates.VERIFICATION: os.getenv('VERIFICATION_EXPIRATION'),
    SessionStates.PAYMENT: os.getenv('PAYMENT_EXPIRATION'),
    SessionStates.STASHING: os.getenv('STASHING_EXPIRATION'),
    SessionStates.HOLD: os.getenv('HOLD_EXPIRATION'),
    SessionStates.RETRIEVAL: os.getenv('RETRIEVAL_EXPIRATION'),
}


class QueueItemModel(Document):  # pylint: disable=too-many-ancestors
    """Queue of session awaiting verification / payment at a station terminal.
        The position of each queued session is determined dynamically
        by its state and time of registration"""
    id: Optional[ObjId] = Field(None, alias="_id")

    queue_type: QueueTypes = Field(
        QueueTypes.USER, description="The type of action being queued/awaited.")

    assigned_session: Link[SessionModel] = Field(
        None, description="The session this queue item handles.")

    assigned_station: Link[StationModel] = Field(
        None, description="The station assigned to the related session.")

    queue_state: QueueStates = Field(
        QueueStates.QUEUED,
        description='State of the queue item. Not related to the session state.')

    queued_state: SessionStates = Field(
        SessionStates.EXPIRED,
        description="The next state of the queued session after activation.")

    timeout_states: List[SessionStates] = Field(
        default=[SessionStates.EXPIRED],
        description="List of states the assigned session takes on after expiring, \
        each list item is a next try for this queue.")

    expiration_window: int = Field(
        0, description="The time in seconds until the queue expires.")

    expires_at: Optional[datetime] = Field(
        None, description="The timestamp when the queue will time out.")

    created_at: datetime = Field(
        datetime.now(),
        description="The datetime when the queue item was created.")

    activated_at: Optional[datetime] = Field(
        None, description="The datetime when the queue item was activated.")

    completed: Optional[datetime] = Field(
        None, description="The datetime when the queue item was completed or expired.")

    @after_event(Update)
    def report_state(self) -> None:
        """Log database operation."""
        logger.debug(f"QueueItem '{self.id}' set to state {
                     self.queue_state}.")

    @dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "queue"
