"""This module provides the Models for Session management."""
# Basics
# Types
import dataclasses
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Union
from uuid import UUID

# Beanie
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import SaveChanges,  View, after_event
from pydantic import Field

# Models
from src.models.station_models import StationModel
from src.models.locker_models import LockerModel
from src.models.user_models import UserModel
# Services
from src.services import websocket_services
from src.services.logging_services import logger


class SessionTypes(str, Enum):
    """All possible types of session (services)"""
    PERSONAL = "personal"
    DROPOFF = "dropOff"
    CLICKCOLLECT = "clickCollect"
    PICKUP = "pickUp"
    RETOUR = "retour"


class SessionStates(str, Enum):
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
    CANCELLED = "cancelled"
    # Session has expired but locker remained open
    STALE = "stale"
    # Session has expired because user exceeded a time window
    EXPIRED = "expired"
    # Session has expired due to internal failure / no response from station
    ABORTED = "aborted"


ACTIVE_SESSION_STATES: List[SessionStates] = [
    SessionStates.CREATED,
    SessionStates.ACTIVE,
    SessionStates.PAYMENT_SELECTED,
    SessionStates.VERIFICATION,
    SessionStates.STASHING,
    SessionStates.HOLD,
    SessionStates.PAYMENT,
    SessionStates.RETRIEVAL
]

SESSION_STATE_TIMEOUTS: Dict[SessionStates, int] = {
    SessionStates.CREATED: 60,
    SessionStates.PAYMENT_SELECTED: 120,
    SessionStates.VERIFICATION: 60,
    SessionStates.STASHING: 90,
    SessionStates.ACTIVE: 86400,
    SessionStates.HOLD: 300,
    SessionStates.PAYMENT: 60,
    SessionStates.RETRIEVAL: 90,
    SessionStates.COMPLETED: 0,
    SessionStates.CANCELLED: 0,
    SessionStates.STALE: 0,
    SessionStates.EXPIRED: 0,
    SessionStates.ABORTED: 0
}

FOLLOW_UP_STATES: Dict[SessionStates, Union[SessionStates, None]] = {
    SessionStates.CREATED: SessionStates.PAYMENT_SELECTED,
    SessionStates.PAYMENT_SELECTED: SessionStates.VERIFICATION,
    SessionStates.VERIFICATION: SessionStates.STASHING,
    SessionStates.STASHING: SessionStates.ACTIVE,
    SessionStates.ACTIVE: SessionStates.PAYMENT,
    SessionStates.HOLD: SessionStates.PAYMENT,
    SessionStates.PAYMENT: SessionStates.RETRIEVAL,
    SessionStates.RETRIEVAL: SessionStates.COMPLETED,
    SessionStates.COMPLETED: None,
    SessionStates.CANCELLED: None,
    SessionStates.STALE: None,
    SessionStates.EXPIRED: None,
    SessionStates.ABORTED: None
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

    user: Link[UserModel] = Field(  # TODO: Remove union here
        None, description="The assigned user to this session.")

    created_ts: datetime = Field(
        datetime.now(), description="Datetime of session creation.")

    ### Session Properties ###
    session_type: SessionTypes = Field(
        default=SessionTypes.PERSONAL, description="The type of session service.\
            Affects price and session flow.")
    payment_method: Optional[PaymentTypes] = Field(
        default=PaymentTypes.TERMINAL, description="The type of payment method.\
            Affects ability to hold and resume sessions.")

    ### State management ###
    session_state: SessionStates = Field(
        default=SessionStates.CREATED, description="The current, internal set session state.")

    # Statistics
    total_duration: Optional[timedelta] = Field(
        None,
        description=("Total duration between session creation and completion.",
                     "This value is only being calculated on demand and can be None."))

    ### Status Broadcasting ###
    @after_event(SaveChanges)
    async def notify_state(self):
        """Send an update message regarding the session state to the mqtt broker."""
        await websocket_services.send_text(session_id=self.id, text=self.session_state)

    @after_event(SaveChanges)
    async def log_state_change(self):
        """Log the state change."""
        logger.debug(
            f"Session '#{self.id}' moved to {self.session_state}."
        )

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "sessions"
        use_state_management = True
        use_cache = False
        # Set the expiration time to one second so the session state is not cached over requests
        # cache_expiration_time = timedelta(seconds=1)
        # cache_capacity = 5


class SessionView(View):
    """Used for serving information about an active session"""
    # Identification
    id: ObjId
    assigned_station: ObjId = Field(
        description="Station at which the session takes place")

    user: UUID = Field(
        None, description="The assigned user to this session.")

    locker_index: Optional[int] = Field(
        default=None, description="Local index of the locker at its station")

    session_type: SessionTypes = Field(
        None, description="Type of session")

    session_state: SessionStates = Field(
        None, description="Current state of the session")

    created_ts: datetime = Field(
        datetime.now(), description="Datetime of session creation.")

    @dataclasses.dataclass
    class Config:  # pylint: disable=missing-class-docstring
        from_attributes = True

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        source = SessionModel
        projection = {
            "id": "$_id",
            "user": "$user",
            "session_state": "$session_state.name",
            "session_type": "$session_type",
            "assigned_station": "$assigned_station._id",
            "locker_index": "$assigned_locker.station_index"
        }


class CompletedSession(View):
    """Used for serving information about a completed session"""
    id: ObjId = Field(alias="_id")
    station: ObjId
    locker: Optional[int] = None
    serviceType: SessionTypes
    state: SessionStates

    # Important timestamps
    started_ts: datetime
    completed_ts: datetime

    # These values can be calculated with the createSummary method
    finalPrice: Optional[float] = None
    totalDuration: Optional[float] = None
    activeDuration: Optional[float] = None

    @dataclasses.dataclass
    class Config:  # pylint: disable=missing-class-docstring
        from_attributes = True
