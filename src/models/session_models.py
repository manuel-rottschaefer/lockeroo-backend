"""This module provides the Models for Session management."""
# Basics
from configparser import ConfigParser
from secrets import token_urlsafe
from random import choice, randint
# Types
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from enum import Enum
from uuid import UUID, uuid4
from bson.objectid import ObjectId
from typing_extensions import Annotated
# Beanie
from beanie import Document, Insert, Link
from beanie import PydanticObjectId as ObjId
from beanie import View, after_event, before_event
from pydantic import Field, PydanticUserError, StringConstraints
# Models
from src.models.station_models import StationModel
from src.models.locker_models import LockerModel
from src.models.user_models import UserModel
# Services
from src.services import websocket_services
from src.services.logging_services import logger_service as logger

base_config = ConfigParser()
base_config.read('.env')


class SessionType(str, Enum):
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
    # The session got a request or information that should not occur
    TERMINATED = "terminated"


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
    SessionState.CREATED: float(
        base_config.get("SESSION_EXPIRATIONS", 'CREATED', fallback='5')),
    SessionState.PAYMENT_SELECTED: float(
        base_config.get("SESSION_EXPIRATIONS", 'PAYMENT_SELECTED', fallback='5')),
    SessionState.VERIFICATION: float(
        base_config.get("SESSION_EXPIRATIONS", 'VERIFICATION', fallback='5')),
    SessionState.STASHING: float(
        base_config.get("SESSION_EXPIRATIONS", 'STASHING', fallback='5')),
    SessionState.ACTIVE: float(
        base_config.get("SESSION_EXPIRATIONS", 'ACTIVE', fallback='5')),
    SessionState.HOLD: float(
        base_config.get("SESSION_EXPIRATIONS", 'HOLD', fallback='5')),
    SessionState.PAYMENT: float(
        base_config.get("SESSION_EXPIRATIONS", 'PAYMENT', fallback='5')),
    SessionState.RETRIEVAL: float(
        base_config.get("SESSION_EXPIRATIONS", 'RETRIEVAL', fallback='5')),
    SessionState.COMPLETED: float(
        base_config.get("SESSION_EXPIRATIONS", 'COMPLETED', fallback='5')),
    SessionState.CANCELED: float(
        base_config.get("SESSION_EXPIRATIONS", 'CANCELED', fallback='5')),
    SessionState.STALE: float(
        base_config.get("SESSION_EXPIRATIONS", 'STALE', fallback='5')),
    SessionState.EXPIRED: float(
        base_config.get("SESSION_EXPIRATIONS", 'EXPIRED', fallback='5')),
    SessionState.ABORTED: float(
        base_config.get("SESSION_EXPIRATIONS", 'ABORTED', fallback='5')),
}


SESSION_STATE_FLOW: Dict[SessionState, SessionState] = {
    SessionState.CREATED: SessionState.PAYMENT_SELECTED,
    SessionState.PAYMENT_SELECTED: SessionState.VERIFICATION,
    SessionState.VERIFICATION: SessionState.STASHING,
    SessionState.STASHING: SessionState.ACTIVE,
    SessionState.ACTIVE: SessionState.PAYMENT,
    SessionState.HOLD: SessionState.ACTIVE,
    SessionState.PAYMENT: SessionState.RETRIEVAL,
    SessionState.RETRIEVAL: SessionState.COMPLETED,
    SessionState.COMPLETED: SessionState.COMPLETED,
    SessionState.CANCELED: SessionState.CANCELED,
    SessionState.STALE: SessionState.STALE,
    SessionState.EXPIRED: SessionState.EXPIRED,
    SessionState.ABORTED: SessionState.ABORTED
}


class PaymentMethod(str, Enum):
    """All possible payment methods."""
    TERMINAL = "terminal"
    APP = "app"


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
    service_type: SessionType = Field(
        default=SessionType.PERSONAL, description="The type of session service.\
            Affects price and session flow.")
    payment_method: Optional[PaymentMethod] = Field(
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

    @before_event(Insert)
    async def set_creation_data(self):
        self.created_at = datetime.now()
        self.websocket_token = websocket_services.generate_token()

    @after_event(Insert)
    async def log_creation(self):
        await self.fetch_link(SessionModel.assigned_locker)
        logger.debug(
            (f"Created session '#{self.id}' at locker "  # pylint: disable=no-member
             f"'#{self.assigned_locker.id}'."))  # pylint: disable=no-member

    @dataclass
    class Settings:
        name = "sessions"
        use_state_management = True
        state_management_save_previous = False
        use_revision = False
        use_cache = False

    @dataclass
    class Config:
        json_schema_extra = {
            "assigned_station": str(ObjectId()),
            "assigned_locker": str(ObjectId()),
            "user": str(ObjectId()),
            "service_type": choice(list(SessionType)),
            "payment_method": choice(list(PaymentMethod)),
            "session_state": choice(list(SessionState)),
            "created_at": datetime.fromtimestamp(0, tz=timezone.utc),
        }


class SessionView(View):
    """Used for serving information about an active session"""
    id: ObjId = Field(alias=None)
    user: UUID
    station: Annotated[str, StringConstraints(
        min_length=6, max_length=6, pattern=r"^[A-Z]{6}$")]
    service_type: SessionType
    session_state: SessionState
    locker_index: int

    @classmethod
    def from_document(cls, session: SessionModel) -> "SessionView":
        return cls(
            id=str(session.id),
            user=session.assigned_user.fief_id,
            station=session.assigned_station.callsign,
            service_type=session.service_type,
            session_state=session.session_state,
            locker_index=session.assigned_locker.station_index)

    @dataclass
    class Settings:
        source = SessionModel
        projection = {
            "id": {"$toString": "$_id"},
            "user": "$assigned_user.fief_id",
            "station": "$assigned_station.callsign",
            "service_type": 1,
            "session_state": "$session_state",
            "locker_index": "$assigned_locker.station_index",
        }

    @dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "id": str(ObjectId()),
            "user": uuid4(),
            "station": "MUCODE",
            "service_type": choice(list(SessionType)),
            "session_state": choice(list(SessionState)),
            "locker_index": randint(1, 10)
        }


class ReducedSessionView(View):
    """Used for serving information about an active session"""
    id: ObjId = Field(alias=None)
    assigned_locker: ObjId
    session_state: SessionState

    @dataclass
    class Settings:
        source = SessionModel
        projection = {
            "id": {"$toString": "$_id"},
            "session_state": "$session_state",
            "assigned_locker": "$assigned_locker._id"
        }

    @dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "id": str(ObjectId()),
            "assigned_locker": str(ObjectId()),
            "session_state": choice(list(SessionState)),
        }


class CreatedSessionView(SessionView):
    """Used for serving information about an active session"""
    websocket_token: str

    @classmethod
    def from_document(cls, session: SessionModel) -> "CreatedSessionView":
        return cls(
            id=session.id,
            user=session.assigned_user.fief_id,
            station=session.assigned_station.callsign,
            locker_index=session.assigned_locker.station_index,
            service_type=session.service_type,
            session_state=session.session_state,
            websocket_token=session.websocket_token)

    @dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "websocket_token": token_urlsafe()
        }


class ActiveSessionView(SessionView):
    """Used for serving information about an active session"""
    queue_position: int

    @classmethod
    def from_position(
            cls, session: SessionModel, position: int) -> "ActiveSessionView":
        return cls(
            id=session.id,
            user=session.assigned_user.fief_id,
            station=session.assigned_station.callsign,
            locker_index=session.assigned_locker.station_index,
            service_type=session.service_type,
            session_state=session.session_state,
            queue_position=position)

    @dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "id": str(ObjectId()),
            "user": uuid4(),
            "station": "MUCODE",
            "service_type": choice(list(SessionType)),
            "session_state": str(SessionState.ACTIVE),
            "queue_position": randint(1, 10)
        }


class ConcludedSessionView(SessionView):
    """Used for serving information about a completed session"""
    total_duration: float
    active_duration: float

    @classmethod
    def from_document(cls, session: SessionModel) -> "ConcludedSessionView":
        return cls(
            id=session.id,
            user=session.assigned_user.fief_id,
            station=session.assigned_station.callsign,
            locker_index=session.assigned_locker.station_index,
            service_type=session.service_type,
            session_state=session.session_state,
            total_duration=session.total_duration.total_seconds(),
            active_duration=session.active_duration.total_seconds()
        )

    @dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "id": str(ObjectId()),
            "station": "MUCODE",
            "locker_index": randint(1, 10),
            "service_type": choice(list(SessionType)),
            "session_state": str(SessionState.COMPLETED),
            "total_duration": randint(300, 3000),
            "activeDuration": randint(300, 3000)
        }


class WebsocketUpdate(View):
    """Used for serving information about an active session"""
    # Identification
    id: ObjId = Field(None, alias="_id")
    session_state: str
    timeout: Optional[datetime]
    queue_position: Optional[int]

    @dataclass
    class Settings:
        source = SessionModel
        projection = {
            "id": "$_id",
            "session_state": "$session_state",
            "timeout": "$timeout",
            "queue_position": "$queue_position"
        }

    @dataclass
    class Config:
        from_attributes = True
        json_schema_extra = {
            "id": str(ObjectId()),
            "session_state": choice(list(SessionState)),
            "timeout": datetime.fromtimestamp(0, tz=timezone.utc),
            "queue_position": randint(1, 10)
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
