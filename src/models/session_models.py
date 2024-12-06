"""This module provides the Models for Session management."""
# Basics
from datetime import datetime, timedelta
from enum import Enum

# Types
import dataclasses
from uuid import UUID
from typing import Optional, Dict, Union
from pydantic import Field

# Beanie
from beanie import Document, Link, View, Update, after_event
from beanie import PydanticObjectId as ObjId

# Models
from src.models.station_models import StationModel
from src.models.locker_models import LockerModel
from src.models.account_models import AccountModel

# Services
from src.services import websocket_services


class SessionTypes(str, Enum):
    """All possible types of session (services)"""
    PERSONAL = "personal"
    DROPOFF = "dropOff"
    CLICKCOLLECT = "clickCollect"
    PICKUP = "pickUp"
    RETOUR = "retour"


class SessionStates(Dict, Enum):
    """A complete list of all session states with their timeout duration in seconds,
    whether the session is considered as 'active' in that state
    and the default follow-up session state."""
    # Session created and assigned to locker. Awaiting payment selection
    CREATED = {"name": "CREATED", "timeout_secs": 180,
               "is_active": True, "next": 'PAYMENT_SELECTED'}
    # Payment method has been selected, now awaiting request to open locker
    PAYMENT_SELECTED = {"name": "PAYMENT_SELECTED", "timeout_secs": 90,
                        "is_active": True, "next": 'VERIFICATION'}
    # Terminal is awaiting verification
    VERIFICATION = {"name": "VERIFICATION", "timeout_secs": 60,
                    "is_active": True, "next": 'STASHING'}
    # Locker opened for the first time, stashing underway.
    STASHING = {"name": "STASHING", "timeout_secs": 120,
                "is_active": True, "next": 'ACTIVE'}
    # Locker closed and session timer is running
    ACTIVE = {"name": "ACTIVE", "timeout_secs": 86400,
              "is_active": True, "next": 'PAYMENT'}
    # Locker opened for retrieving stuff (only digital payment)
    HOLD = {"name": "HOLD", "timeout_secs": 300,
            "is_active": True, "next": 'ACTIVE'}
    # Payment is pending at the terminal
    PAYMENT = {"name": "PAYMENT", "timeout_secs": 60,
               "is_active": True, "next": 'RETRIEVAL'}
    # Locker opens a last time for retrieval
    RETRIEVAL = {"name": "RETRIEVAL", "timeout_secs": 120,
                 "is_active": True, "next": 'COMPLETED'}

    # Session has been completed (paid for, locker closed)
    COMPLETED = {"name": "COMPLETED", "timeout_secs": 0,
                 "is_active": False, "next": ''}
    # Session has been canceled, no active time, no payment
    CANCELLED = {"name": "CANCELLED", "timeout_secs": 0,
                 "is_active": False, "next": ''}
    # Session has expired but locker remained open
    STALE = {"name": "STALE", "timeout_secs": 0,
             "is_active": False, "next": ''}
    # Session has expired because user exceeded a time window
    EXPIRED = {"name": "EXPIRED", "timeout_secs": 0,
               "is_active": False, "next": ''}
    # Session has expired due to internal failure / no response from station
    ABORTED = {"name": "ABORTED", "timeout_secs": 0,
               "is_active": False, "next": ''}


class PaymentTypes(str, Enum):
    """All possible payment methods."""
    TERMINAL = "terminal"
    ONLINE = "online"


class SessionModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a session in the database.
         All relevant timestamps are stored in actions."""
    ### Identification ###
    id: Optional[ObjId] = Field(None, alias="_id")
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
    is_active: bool = Field(
        default=True, description="Maps the session state activeness into the database.")

    # Statistics
    total_duration: Optional[timedelta] = Field(
        None,
        description=("Total duration between session creation and completion.",
                     "This value is only being calculated on demand and can be None."))

    ### Status Broadcasting ###
    @after_event(Update)
    async def notify_state(self):
        """Send an update message regarding the session state to the mqtt broker."""
        await websocket_services.send_text(socket_id=self.id, text=self.session_state)

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

    assigned_account: UUID = Field(
        None, description="The assigned user to this session.")

    locker_index: Optional[int] = Field(
        default=None, description="Local index of the locker at its station")

    session_type: SessionTypes = Field(
        None, description="Type of session")

    session_state: str = Field(
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
            "assigned_account": "$assigned_account",
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
