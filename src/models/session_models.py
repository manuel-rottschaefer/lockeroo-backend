"""
    Session Models
"""

# Basics
from datetime import datetime, timedelta
from enum import Enum

# Types
import dataclasses
from typing import Optional, List
from uuid import UUID
from pydantic import Field

# Beanie
from beanie import Document, Link, View, Update, after_event
from beanie import PydanticObjectId as ObjId

# Models
from src.models.station_models import StationModel
from src.models.locker_models import LockerModel

# Services
from src.services import websocket_services


class SessionTypes(str, Enum):
    """All possible types of session (services)"""
    PERSONAL = "personal"
    DROPOFF = "dropOff"
    CLICKCOLLECT = "clickCollect"
    PICKUP = "pickUp"
    RETOUR = "retour"


class SessionStates(str, Enum):
    """All possible states a session can be in."""
    # Session created and assigned to locker. Awaiting payment selection
    CREATED = "created"
    # Payment method has been selected, now awaiting request to open locker
    PAYMENT_SELECTED = "payment_selected"
    # Terminal is awaiting verification
    VERIFICATION = "verification"
    # Locker opened for the first time, stashing underway. This phase may only
    # last 3 minutes max
    STASHING = 'stashing'
    # Locker closed and session timer is running
    ACTIVE = "active"
    # Locker opened for retriving stuff (only digital payment)
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
    STALE = 'stale'
    # Session has expired due to exceeded time window by user
    EXPIRED = "expired"
    # Session has expired due to internal failure / no response from station
    ABORTED = "aborted"


class SessionPaymentTypes(str, Enum):
    """All possible payment methods."""
    TERMINAL = "terminal"
    ONLINE = "online"


INACTIVE_SESSION_STATES: List[SessionStates] = [
    SessionStates.COMPLETED,
    SessionStates.CANCELLED,
    SessionStates.STALE,
    SessionStates.EXPIRED,
    SessionStates.ABORTED
]


class SessionModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a session in the database.
         All relevant timestamps are stored in actions."""
    ### Identification ###
    id: Optional[ObjId] = Field(None, alias="_id")
    assigned_station: Link[StationModel] = Field(
        description="The assigned station to this session.")

    assigned_locker: Link[LockerModel] = Field(
        description="The assigned locker to this session.")

    assigned_user: UUID = Field(
        None, description="The assigned user to this session.")

    created_ts: datetime = Field(
        datetime.now(), description="Datetime of session creation.")

    ### Session Properties ###
    session_type: SessionTypes = Field(
        default=SessionTypes.PERSONAL, description="The type of session service.\
            Affects price and user flow.")
    payment_method: Optional[SessionPaymentTypes] = Field(
        default=SessionPaymentTypes.TERMINAL, description="The type of payment method.\
            Affects ability to hold and resume sessions.")

    ### State management ###
    session_state: SessionStates = Field(
        default=SessionStates.CREATED, description="The current, internal set session state.")

    ### Status Broadcasting ###
    @after_event(Update)
    async def notify_state(self):
        """Send an update message regarding the session state to the mqtt broker."""
        await websocket_services.send_text(socket_id=self.id, text=self.session_state)

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "sessions"
        use_cache = True
        # TODO: Evaluate caching as this can lead to improper state handling. Maybe refresh single keys?
        # cache_expiration_time = timedelta(seconds=10)
        # cache_capacity = 5

    @dataclasses.dataclass
    class Config:  # pylint: disable=missing-class-docstring
        arbitrary_types_allowed = True


class SessionView(View):
    """Used for serving information about an active session"""
    # Identification
    id: ObjId
    assigned_station: Link[StationModel] = Field(
        description="Station at which the session takes place")

    assigned_user: UUID = Field(
        None, description="The assigned user to this session.")

    locker_index: Optional[int] = Field(
        default=None, description="Local index of the locker at its station")

    session_type: SessionTypes = Field(
        default=SessionTypes.PERSONAL, description="Type of session")

    session_state: SessionStates = Field(
        default=SessionStates.CREATED, description="Current state of the session")

    created_ts: datetime = Field(
        datetime.now(), description="Datetime of session creation.")

    @dataclasses.dataclass
    class Config:  # pylint: disable=missing-class-docstring
        from_attributes = True

    @dataclasses.dataclass
    class Setttings:  # pylint: disable=missing-class-docstring
        source = SessionModel


class CompletedSession(View):
    """Used for serving information about a completed session"""
    id: Optional[ObjId] = Field(None, alias="_id")
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
