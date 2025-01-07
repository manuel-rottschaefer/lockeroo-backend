"""This module provides the Models for Session management."""
# Basics
from os import getenv
# Types
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Union
from uuid import UUID

# Beanie
from beanie import Document, Insert, Link
from beanie import PydanticObjectId as ObjId
from beanie import View, after_event, before_event
from pydantic import Field, PydanticUserError

from src.models.locker_models import LockerModel
# Models
from src.models.station_models import StationModel
from src.models.user_models import UserModel
# Services
from src.services import websocket_services
from src.services.logging_services import logger_service as logger


class SessionTypes(str, Enum):
    """All possible types of session (services)"""
    PERSONAL = "personal"
    DROPOFF = "dropOff"
    CLICKCOLLECT = "clickCollect"
    PICKUP = "pickUp"
    RETOUR = "retour"


class SessionState(str, Enum):
    """A complete list of all session states with their timeout duration in seconds,
    whether the session is considered as 'active' in that state
    and the default follow-up session state."""
    # Session created and assigned to locker. Awaiting payment selection
    CREATED = "created"
    # Payment method has been selected, now awaiting request to open locker
    PAYMENT_SELECTED = "paymentSelected"
    # Terminal is awaiting verification
    VERIFICATION = "verification"
    # Locker opened for the first time, stashing underway.
    STASHING = "stashing"
    # Locker closed and session timer is running
    ACTIVE = "active"
    # Locker opened for retrieving stuff (only digital payment)
    HOLD = "hold"
    # Payment is pending at the terminal
    PAYMENT = "payment"
    # Locker opens a last time for retrieval
    RETRIEVAL = "retrieval"

    # Session has been completed (paid for, locker closed)
    COMPLETED = "completed"
    # Session has been canceled, no active time, no payment
    CANCELED = "canceled"
    # Session has expired but locker remained open
    STALE = "stale"
    # Session has expired because user exceeded a time window
    EXPIRED = "expired"
    # Session has expired due to internal failure / no response from station
    ABORTED = "aborted"
    # User has left his stuff in the locker
    ABANDONED = "abandoned"


ACTIVE_SESSION_STATES: List[SessionState] = [
    SessionState.CREATED,
    SessionState.ACTIVE,
    SessionState.PAYMENT_SELECTED,
    SessionState.VERIFICATION,
    SessionState.STASHING,
    SessionState.HOLD,
    SessionState.PAYMENT,
    SessionState.RETRIEVAL
]

SESSION_TIMEOUTS: Dict[SessionState, int] = {
    SessionState.CREATED: float(getenv("CREATED", '0')),
    SessionState.PAYMENT_SELECTED: float(getenv("PAYMENT_SELECTED", '0')),
    SessionState.VERIFICATION: float(getenv("VERIFICATION", '0')),
    SessionState.STASHING: float(getenv("STASHING", '0')),
    SessionState.ACTIVE: float(getenv("ACTIVE", '0')),
    SessionState.HOLD: float(getenv("HOLD", '0')),
    SessionState.PAYMENT: float(getenv("PAYMENT", '0')),
    SessionState.RETRIEVAL: float(getenv("RETRIEVAL", '0')),
    SessionState.COMPLETED: float(getenv("COMPLETED", '0')),
    SessionState.CANCELED: float(getenv("CANCELED", '0')),
    SessionState.STALE: float(getenv("STALE", '0')),
    SessionState.EXPIRED: float(getenv("EXPIRED", '0')),
    SessionState.ABORTED: float(getenv("ABORTED", '0'))
}

FOLLOW_UP_STATES: Dict[SessionState, Union[SessionState, None]] = {
    SessionState.CREATED: SessionState.PAYMENT_SELECTED,
    SessionState.PAYMENT_SELECTED: SessionState.VERIFICATION,
    SessionState.VERIFICATION: SessionState.STASHING,
    SessionState.STASHING: SessionState.ACTIVE,
    SessionState.ACTIVE: SessionState.PAYMENT,
    SessionState.HOLD: SessionState.PAYMENT,
    SessionState.PAYMENT: SessionState.RETRIEVAL,
    SessionState.RETRIEVAL: SessionState.COMPLETED,
    SessionState.COMPLETED: None,
    SessionState.CANCELED: None,
    SessionState.STALE: None,
    SessionState.EXPIRED: None,
    SessionState.ABORTED: None
}


class PaymentTypes(str, Enum):
    """All possible payment methods."""
    TERMINAL = "terminal"
    ONLINE = "online"


class SessionModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a session in the database.
         All relevant timestamps are stored in actions."""
    ### Identification ###
    id: ObjId = Field(None, alias="_id")
    assigned_station: Link[StationModel] = Field(
        description="The assigned station to this session.")

    assigned_locker: Link[LockerModel] = Field(
        description="The assigned locker to this session.")

    assigned_user: Link[UserModel] = Field(
        None, description="The assigned user to this session.")

    ### Session Properties ###
    session_type: SessionTypes = Field(
        default=SessionTypes.PERSONAL, description="The type of session service.\
            Affects price and session flow.")
    payment_method: Optional[PaymentTypes] = Field(
        default=None, description="The type of payment method.\
            Affects ability to hold and resume sessions.")

    ### State management ###
    session_state: SessionState = Field(
        default=SessionState.CREATED, description="The current, internal set session state.")

    timeout_count: int = Field(
        0, description="Number of times the session has timed out.")

    ### Required Timestamps ###
    created_at: datetime = Field(
        None, description="Timestamp of session creation."
    )

    completed_at: Optional[datetime] = Field(
        None, description="Timestamp of session completion.")

    # Statistics
    total_duration: Optional[timedelta] = Field(
        None, description="Total duration between session creation and completion.")

    active_duration: Optional[timedelta] = Field(
        None, description="Total duration of active time during the session.")

    ### Security ###
    websocket_token: Optional[str] = Field(
        None, description="Token for websocket communication.")

    @ before_event(Insert)
    async def set_creation_data(self):
        self.created_at = datetime.now()
        self.websocket_token = websocket_services.generate_token()

    @ after_event(Insert)
    async def log_creation(self):
        await self.fetch_link(SessionModel.assigned_locker)
        logger.debug(
            (f"Created session '#{self.id}' for user "
             f"'#{self.assigned_user.id}' at locker "  # pylint: disable=no-member
             f"'#{self.assigned_locker.id}'."))  # pylint: disable=no-member

    @ dataclass
    class Settings:
        name = "sessions"
        use_state_management = True
        state_management_save_previous = False
        use_revision = False
        use_cache = False

    @ dataclass
    class Config:
        json_schema_extra = {
            "assigned_station": "60d5ec49f1d2b2a5d8f8b8b8",
            "assigned_locker": "60d5ec49f1d2b2a5d8f8b8b8",
            "user": "60d5ec49f1d2b2a5d8f8b8b8",
            "session_type": "personal",
            "payment_method": "terminal",
            "session_state": "created",
            "created_at": "2023-10-10T10:00:00"
        }


class SessionView(View):
    """Used for serving information about an active session"""
    # Identification
    id: str
    assigned_user: UUID

    station: str
    locker_index: int

    service_type: SessionTypes
    session_state: SessionState

    # TODO: Implement a timestamping mechanism

    @ dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "assigned_station": "CENTRAL",
            "user": "12345678-1234-5678-1234-567812345678",
            "station_index": 1,
            "session_type": "personal",
            "session_state": "created"
        }

    @ dataclass
    class Settings:
        source = SessionModel
        is_root = False
        projection = {
            "id": {"$toString": "$_id"},
            "user": "$user.fief_id",
            "assigned_station": {"$toString": "$assigned_station._id"},
            "station_index": "$assigned_locker.station_index",
            "session_type": "$session_type",
            "session_state": "$session_state.name",
        }


class ReducedSessionView(View):
    """Used for serving information about an active session"""
    id: str
    session_state: SessionState
    assigned_locker: str

    @ dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "session_state": "created",
            "assigned_locker": "60d5ec49f1d2b2a5d8f8b8b8"
        }

    @ dataclass
    class Settings:
        source = SessionModel
        projection = {
            "id": {"$toString": "$_id"},
            "session_state": "$session_state",
            "assigned_locker": {"$toString": "$assigned_locker._id"}
        }


class CreatedSessionView(SessionView):
    websocket_token: str

    @ dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "websocket_token": "60d5ec49f1d2b2a5d8f8b8b8"
        }


class ActiveSessionView(SessionView):
    """Used for serving information about an active session"""
    queue_position: Optional[int]

    @ dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "queue_position": 1
        }


class WebsocketUpdate(View):
    """Used for serving information about an active session"""
    # Identification
    id: str
    session_state: str
    timeout: Optional[datetime]
    queue_position: Optional[int]

    @ dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "session_state": "created",
            "timeout": "2023-10-10T10:00:00",
            "queue_position": 1
        }


class ConcludedSessionView(View):
    """Used for serving information about a completed session"""
    id: str
    station: str
    locker_index: int
    service_type: SessionTypes
    session_state: SessionState

    # These values can be calculated with the createSummary method
    # finalPrice: Optional[float] = None
    total_duration: float
    active_duration: float

    @ dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "station": "MUCODE",
            "locker_index": 1,
            "service_type": "personal",
            "session_state": "completed",
            "total_duration": 100,
            "activeDuration": 50
        }


try:
    models = [SessionModel,
              SessionView,
              ReducedSessionView,
              CreatedSessionView,
              ActiveSessionView,
              WebsocketUpdate,
              ConcludedSessionView]
    for model in models:
        model.model_json_schema()
except PydanticUserError as exc_info:
    assert exc_info.code == 'invalid-for-json-schema'
