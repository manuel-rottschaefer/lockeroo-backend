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


EXPIRATION_STATE_MAP: Dict[SessionStates, SessionStates] = {
    # TODO: Queue has to be able to requeue again
    SessionStates.VERIFICATION_PENDING: SessionStates.VERIFICATION_QUEUED,
    SessionStates.PAYMENT_PENDING: SessionStates.PAYMENT_QUEUED,
    SessionStates.STASHING: SessionStates.STALE,
}

EXPIRATION_DURATIONS: Dict[SessionStates, int] = {
    SessionStates.VERIFICATION_PENDING: os.getenv('VERIFICATION_EXPIRATION'),
    SessionStates.PAYMENT_PENDING: os.getenv('PAYMENT_EXPIRATION'),
}


class QueueItemModel(Document):  # pylint: disable=too-many-ancestors
    """Queue of session awaiting verification / payment at a station terminal.
        The position of each queued session is determined dynamically
        by its state and time of registration"""
    id: Optional[ObjId] = Field(None, alias="_id")

    assigned_session: ObjId
    assigned_station: ObjId
    queue_state: QueueStates
    registered_ts: datetime

    @after_event(Replace)
    def report_state(self):
        """Log database operation."""
        logger.debug(f"Queue item '{self.id}' set to state {
                     self.queue_state}.")

    @dataclass
    class Settings:
        """Name in database"""
        name = "queue"
