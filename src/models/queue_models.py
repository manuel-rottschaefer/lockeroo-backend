"""
Queue Item Models
"""

# Types
import os
from dotenv import load_dotenv
from enum import Enum
from typing import Optional, Dict
from datetime import datetime
from dataclasses import dataclass
from pydantic import Field

# Beanie
from beanie import Document, Replace, after_event
from beanie import PydanticObjectId as ObjId

# Models
from src.models.session_models import SessionStates

# Logging
from src.services.logging_services import logger

load_dotenv('environments/.env')


class QueueStates(str, Enum):
    """States for a terminal queue"""
    QUEUED = "queued"               # Session is queued for verification/payment
    PENDING = "pending"             # Session is awaiting verification/payment
    COMPLETED = "completed"         # Session has been verified/paid
    EXPIRED = "expired"             # Session has expired


EXPIRATION_DURATIONS: Dict[SessionStates, int] = {
    SessionStates.VERIFICATION: os.getenv('VERIFICATION_EXPIRATION'),
    SessionStates.PAYMENT: os.getenv('PAYMENT_EXPIRATION'),
}


class QueueItemModel(Document):  # pylint: disable=too-many-ancestors
    """Queue of session awaiting verification / payment at a station terminal.
        The position of each queued session is determined dynamically
        by its state and time of registration"""
    id: Optional[ObjId] = Field(None, alias="_id")

    assigned_session: ObjId = Field(
        None, description="The session this queue item handles.")
    assigned_station: ObjId = Field(
        None, description="The station assigned to the related session.")

    queue_state: QueueStates = Field(
        QueueStates.QUEUED, description='State of the queue item. Not related to the session state.')

    queued_state: SessionStates = Field(
        SessionStates.EXPIRED, description="The next state of the queued session after activation.")

    # TODO: Required?
    timeout_state: SessionStates = Field(
        SessionStates.EXPIRED, description="The state of the session after expiration of a queue.")

    registered_ts: datetime = Field(
        datetime.now(), description="The datetime when the queue item was created.")

    activated_ts: Optional[datetime] = Field(
        None, description="The datetime when the queue item was activated.")

    completed: Optional[datetime] = Field(
        None, description="The datetime when the queue item was completed or expired.")

    @after_event(Replace)
    def report_state(self) -> None:
        """Log database operation."""
        logger.debug(f"Queue item '{self.id}' set to state {
                     self.queue_state}.")

    @dataclass
    class Settings:
        """Name in database"""
        name = "queue"
