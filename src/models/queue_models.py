'''
Queue Item Models
'''

# Types
from enum import Enum
from typing import Optional
from datetime import datetime
from dataclasses import dataclass
from pydantic import Field

# Beanie
from beanie import Document, Replace, after_event
from beanie import PydanticObjectId as ObjId

# Logging
from ..services.logging_services import logger


class QueueStates(str, Enum):
    '''States for a terminal queue'''
    QUEUED = "queued"               # Session is queued for verification/payment
    PENDING = "pending"             # Session is awaiting verification/payment
    COMPLETED = "completed"         # Session has been verified/paid
    EXPIRED = "expired"             # Session has expired


class QueueItemModel(Document):  # pylint: disable=too-many-ancestors
    '''Queue of session awaiting verification / payment at a station terminal.
        The position of each queued session is determined dynamically
        by its state and time of registration'''
    id: Optional[ObjId] = Field(None, alias="_id")

    assigned_session: ObjId
    assigned_station: ObjId
    queue_state: QueueStates
    registered_ts: datetime

    @after_event(Replace)
    def report_state(self):
        '''Log database operation.'''
        logger.debug(f"Queue item for session '{
                     self.assigned_session}' updated to state '{self.queue_state}'.")

    @dataclass
    class Settings:
        '''Name in database'''
        name = "queue"
