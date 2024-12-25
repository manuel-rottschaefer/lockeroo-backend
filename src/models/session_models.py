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
from beanie import (
    SaveChanges, Insert, View, before_event, after_event)
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
    CANCELLED = "cancelled"
    # Session has expired but locker remained open
    STALE = "stale"
    # Session has expired because user exceeded a time window
    EXPIRED = "expired"
    # Session has expired due to internal failure / no response from station
    ABORTED = "aborted"


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
    SessionState.CREATED: 60,
    SessionState.PAYMENT_SELECTED: 120,
    SessionState.VERIFICATION: 60,
    SessionState.STASHING: 90,
    SessionState.ACTIVE: 86400,
    SessionState.HOLD: 300,
    SessionState.PAYMENT: 60,
    SessionState.RETRIEVAL: 90,
    SessionState.COMPLETED: 0,
    SessionState.CANCELLED: 0,
    SessionState.STALE: 0,
    SessionState.EXPIRED: 0,
    SessionState.ABORTED: 0
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
    SessionState.CANCELLED: None,
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

    user: Link[UserModel] = Field(  # TODO: Remove union here
        None, description="The assigned user to this session.")

    ### Session Properties ###
    session_type: SessionTypes = Field(
        default=SessionTypes.PERSONAL, description="The type of session service.\
            Affects price and session flow.")
    payment_method: Optional[PaymentTypes] = Field(
        default=PaymentTypes.TERMINAL, description="The type of payment method.\
            Affects ability to hold and resume sessions.")

    ### State management ###
    session_state: SessionState = Field(
        default=SessionState.CREATED, description="The current, internal set session state.")

    ### Required Timestamps ###
    created_at: datetime = Field(
        None, description="Timestamp of session creation."
    )

    # Statistics
    total_duration: Optional[timedelta] = Field(
        None, description=("Total duration between session creation and completion.",
                           "This value is only being calculated on demand and can be None."))

    @ before_event(Insert)
    async def set_creation_data(self):
        self.created_at = datetime.now()

    @ after_event(Insert)
    async def log_creation(self):
        logger.debug(
            (f"Created session '#{self.id}' for user "
             f"'#{self.user.id}' at locker '#{self.assigned_locker.callsign}'."))  # pylint: disable=no-member

    @ after_event(SaveChanges)
    async def handle_update(self):
        """Send an update message regarding the session state to the mqtt broker."""
        await websocket_services.send_text(session_id=self.id, text=self.session_state)
        logger.debug(
            f"Session '#{self.id}' moved to {self.session_state}.")

    @ dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "sessions"
        use_state_management = True
        use_revision = False
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

    session_state: SessionState = Field(
        None, description="Current state of the session")

    # These timestamps are only gathered from session actions when a
    # session view isrequested to avoid duplicate data entries
    # TODO: Implement a timestamping mechanism

    @ dataclasses.dataclass
    class Config:  # pylint: disable=missing-class-docstring
        from_attributes = True

    @ dataclasses.dataclass
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
    state: SessionState

    # These values can be calculated with the createSummary method
    finalPrice: Optional[float] = None
    totalDuration: Optional[float] = None
    activeDuration: Optional[float] = None

    @ dataclasses.dataclass
    class Config:  # pylint: disable=missing-class-docstring
        from_attributes = True
