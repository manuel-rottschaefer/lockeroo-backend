"""This module provides the Models for Station management."""
# Types
import dataclasses
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Annotated

# Beanie
from pymongo import TEXT
from beanie import Document, Indexed
from beanie import PydanticObjectId as ObjId
from beanie import SaveChanges, View, after_event
from pydantic import BaseModel, Field

# Services
from src.services.mqtt_services import fast_mqtt
from src.services.logging_services import logger


class StationStates(str, Enum):
    """General status information for physical locker stations,
    relevant for session requests and internal maintenance management."""
    AVAILABLE = "available"  # Station terminal is passive and waiting for sessions
    MAINTENANCE = "maintenance"  # Station terminal is offline for maintenance
    OUTOFSERVICE = "outOfService"  # Station terminal is offline and awaiting repair


class TerminalStates(str, Enum):
    """Modes of station terminals.
    Should always be idle except for short periods when users are interacting."""
    # TODO: Add a watch service that checks whether terminals are reported
    # as out of service or not being idle for longer times.
    IDLE = "idle"  # Terminal is idle
    VERIFICATION = "verification"  # Terminal is in verification mode
    PAYMENT = "payment"  # Terminal is in payment mode
    OUTOFSERVICE = "outOfService"  # Terminal is offline or awaiting repair


class StationType(BaseModel):
    """Config representation of station types."""
    name: str = Field(description="Name of the station type.")
    code: str = Field(description="Short identifier for the type.")
    description: str = Field(
        description="You would've guessed it- a description :)")
    locker_amount: int = Field(
        description="The amount of individual lockers.")
    render: str = Field(description="Path to a static render of the model.")
    has_gsm: bool = Field(
        description="Whether the station has a mobile antenna.")
    has_wifi: bool = Field(
        description="Whether the station has a WiFi antenna.")
    has_solar: bool = Field(
        description="Whether the station can house a solar panel.")
    is_embedded: bool = Field(
        description="Whether the station is embedded into the ground (or has legs).")


class StationModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a station in the database."""
    # Identification
    id: ObjId = Field(alias="_id")
    full_name: str
    callsign: Annotated[str, Indexed(index_type=TEXT, unique=True)]

    # Internal Properties
    station_type: str
    hw_version: str
    sw_version: str

    # Setup and Installation Data
    installation_ts: datetime
    installed_lockers: int

    # Operation state
    station_state: StationStates = Field(default=StationStates.AVAILABLE)
    terminal_state: TerminalStates = Field(default=TerminalStates.IDLE)
    next_service_date: datetime
    service_due: bool

    # Operation history
    total_session_count: int
    total_session_duration: timedelta
    last_service_date: datetime

    # Service states
    is_storage_available: bool
    is_charging_available: bool

    # Location
    city_name: str
    address: str
    location: Dict
    nearby_public_transit: Optional[str]

    @after_event(SaveChanges)
    def notify_station_state(self):
        """Send an update message regarding the session state to the mqtt broker."""
        fast_mqtt.publish(
            f"stations/{self.callsign}/state", self.station_state)

    ### State broadcasting ###
    @after_event(SaveChanges)
    def instruct_terminal_state(self, instruct_state: TerminalStates = None):
        """Send an update message regarding the session state to the mqtt broker."""
        state_to_broadcast = instruct_state if instruct_state is not None else self.terminal_state
        logger.debug(
            (f"Sending {state_to_broadcast} instruction to "
             f"terminal at station '#{self.callsign}'."))
        fast_mqtt.publish(
            message_or_topic=f"stations/{self.callsign}/terminal/instruct",
            payload=state_to_broadcast.upper(),
            qos=2)

    @ dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "stations"
        use_state_management = True
        use_revision = False
        use_cache = False
        # cache_expiration_time = timedelta(seconds=10)
        # cache_capacity = 5


class StationView(View):
    """Public representation of a station"""
    class Settings:  # pylint: disable=missing-class-docstring, too-few-public-methods
        source = StationModel

    # Identification
    id: ObjId = Field(alias="_id")
    full_name: str
    callsign: str

    # Internal Properties
    station_type: str

    # Setup and Installation Data
    installed_lockers: int

    # Operation states
    station_state: StationStates

    is_storage_available: bool
    is_charging_available: bool

    # Location
    city_name: str
    address: str
    location: Dict
    nearby_public_transit: Optional[str]


class StationLockerAvailabilities(View):
    """Availability of each locker type at a station"""
    small: bool
    medium: bool
    large: bool
