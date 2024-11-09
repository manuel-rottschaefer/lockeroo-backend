"""
    Session Models
"""

# Basics
from datetime import datetime
from enum import Enum

# Types
from typing import Optional
from uuid import UUID
from pydantic import Field
import dataclasses

# Beanie
from beanie import Document, View, Replace, after_event
from beanie import PydanticObjectId as ObjId

# Services
from src.services.mqtt_services import fast_mqtt


class SessionTypes(str, Enum):
    """All possible types of session (services)"""
    PERSONAL = "personal"
    DROPOFF = "dropOff"
    CLICKCOLLECT = "clickCollect"
    PICKUP = "pickUp"
    RETOUR = "retour"


class SessionStates(str, Enum):
    """All possible states a session can be in"""
    # Session created and assigned to locker. Awaiting payment selection
    CREATED = "created"
    # Payment method has been selected, now awaiting request to open locker
    # for stowing
    PAYMENT_SELECTED = "payment_selected"
    # Verification at the terminal is queued
    VERIFICATION_QUEUED = "verification_queued"
    # Terminal is awaiting verification
    VERIFICATION_PENDING = "verification"
    # Locker opened for the first time, stashing underway. This phase may only
    # last 3 minutes max
    STASHING = 'stashing'
    # Locker closed and session timer is running
    ACTIVE = "active"
    # Locker opened for retriving stuff (only digital payment)
    HOLD = "hold"
    # Locker is closed/opened and payment is queued
    PAYMENT_QUEUED = "payment_queued"
    # Payment is pending at the terminal
    PAYMENT_PENDING = "payment"
    # Locker opens a last time for retrieval
    RETRIEVAL = "retrieval"
    # Session has been completed (paid for, locker closed)
    COMPLETED = "completed"

    # Session has been canceled, no active time, no payment
    CANCELLED = "cancelled"
    # Session has expired due to exceeded time windows
    EXPIRED = "expired"

    # Only for logging purposes
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"


class SessionPaymentTypes(str, Enum):
    """All possible payment methods"""
    TERMINAL = "terminal"
    ONLINE = "online"


class SessionModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a session in the database.
         All relevant timestamps are stored in actions."""
    ### Identification ###
    id: Optional[ObjId] = Field(None, alias="_id")
    assigned_station: ObjId = Field(
        None, description="The assigned station to this session.")
    assigned_locker: ObjId = Field(
        None, description="The assigned locker to this station.")
    assigned_user: UUID = Field(
        None, description="The assigned user to this station.")

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
    @after_event(Replace)
    def notify_state(self):
        """Send an update message regarding the session state to the mqtt broker."""
        fast_mqtt.publish(f"sessions/{self.id}/notify",
                          self.session_state.value, qos=1)

    @dataclasses.dataclass
    class Settings:
        """Name in Database"""
        name = "sessions"

    @dataclasses.dataclass
    class Config:
        """Configurations"""
        arbitrary_types_allowed = True


class SessionView(View):
    """Used for serving information about an active session"""
    # Identification
    id: ObjId
    assigned_station: ObjId = Field(
        description="Station at which the session takes place")
    locker_index: Optional[int] = Field(
        default=None, description="Local index of the locker at its station")
    session_type: SessionTypes = Field(
        default=SessionTypes.PERSONAL, description="Type of session")
    session_state: SessionStates = Field(
        default=SessionStates.CREATED, description="Current state of the session")

    @dataclasses.dataclass
    class Config:
        """Alias for _id"""
        from_attributes = True


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
    class Config:
        """Alias for _id"""
        from_attributes = True
