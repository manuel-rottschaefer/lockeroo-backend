"""This module provides the Models for Station management."""
# Types
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Dict, List, Optional
# Beanie
from beanie import Document, Indexed
from beanie import PydanticObjectId as ObjId
from beanie import SaveChanges, View, after_event
from pydantic import BaseModel, Field, PydanticUserError
from pymongo import TEXT
# Services
from src.services.mqtt_services import fast_mqtt


class StationState(str, Enum):
    """General status information for physical locker stations,
    relevant for session requests and internal maintenance management."""
    AVAILABLE = "available"         # Station terminal is passive and waiting for sessions
    MAINTENANCE = "maintenance"     # Station terminal is offline for maintenance
    OUTOFSERVICE = "outOfService"   # Station terminal is offline and awaiting repair


class TerminalState(str, Enum):
    """Modes of station terminals.
    Should always be idle except for short periods when users are interacting."""
    IDLE = "idle"  # Terminal is idle
    VERIFICATION = "verification"  # Terminal is in verification mode
    PAYMENT = "payment"  # Terminal is in payment mode
    OUTOFSERVICE = "outOfService"  # Terminal is offline or awaiting repair


class LockerLayout(BaseModel):
    """Representation of the layout of a station."""
    locker_count: int = Field(description="Total amount of lockers.")

    column_count: int = Field(description="Amount of columns of lockers.")
    max_row_count: int = Field(description="Amount of rows of lockers.")

    # Name of locker types from top to bottom, left to right
    layout: List[List[str]]


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
    id: ObjId = Field(None, alias="_id")
    full_name: str = Field(description="Full name of the station.")
    callsign: Annotated[str, Indexed(index_type=TEXT, unique=True)]

    # Internal Properties
    station_type: str = Field(description="Hardware type of the station.")
    hw_version: str = Field(description="Hardware version of the station.")
    sw_version: str = Field(description="Software version of the station.")

    # Setup and Installation Data
    installed_at: datetime = Field(
        description="Date and time of installation.")

    # Layout
    locker_layout: LockerLayout = Field(description="Layout of the station.")

    # Operation state
    station_state: StationState = Field(
        default=StationState.AVAILABLE,
        description="Current state of the station.")
    terminal_state: TerminalState = Field(
        default=TerminalState.IDLE,
        description="Current state of the terminal.")
    scheduled_maintenance_at: datetime = Field(
        description="Date of the next scheduled maintenance.")
    maintenance_due_at: bool = Field(
        description="Whether the station is due for maintenance.")

    # Operation history
    total_session_count: int = Field(
        description="Total amount of sessions completed.")
    total_session_duration: timedelta = Field(
        description="Total duration of all sessions.")
    last_service_date: datetime = Field(
        description="Date of the last maintenance.")

    # Service states
    is_storage_available: bool = Field(
        description="Whether the station has storage available.")
    is_charging_available: bool = Field(
        description="Whether the station has charging available.")

    # Location
    city_name: str = Field(description="Name of the city.")
    address: str = Field(description="Address of the station.")
    location: Dict = Field(description="GPS coordinates of the station.")
    nearby_public_transport: Optional[str] = Field(
        description="Name of nearby public transport.")

    @ after_event(SaveChanges)
    def notify_station_state(self):
        """Send an update message regarding the session state to the mqtt broker."""
        fast_mqtt.publish(
            f"stations/{self.callsign}/state", self.station_state)

    @ dataclass
    class Settings:
        name = "stations"
        use_state_management = True
        use_revision = False
        use_cache = False
        # cache_expiration_time = timedelta(seconds=10)
        # cache_capacity = 5

    @ dataclass
    class Config:
        json_schema_extra = {
            "full_name": "Central Station",
            "callsign": "CENTRAL",
            "station_type": "Type A",
            "hw_version": "1.0",
            "sw_version": "1.0",
            "installed_at": "2023-10-10T10:00:00",
            "installed_lockers": 10,
            "next_service_date": "2023-11-10T10:00:00",
            "service_due": False,
            "total_session_count": 100,
            "total_session_duration": "500:00:00",
            "last_service_date": "2023-09-10T10:00:00",
            "is_storage_available": True,
            "is_charging_available": True,
            "city_name": "City",
            "address": "123 Main St",
            "location": {"lat": 40.7128, "lon": -74.0060},
            "nearby_public_transport": "U Odeonsplatz"
        }


class StationView(View):
    """Public representation of a station"""
    # Identification
    full_name: str
    callsign: str

    # Properties
    station_type: str
    is_storage_available: bool
    is_charging_available: bool

    # Operation states
    station_state: StationState

    # Location
    city_name: str
    address: str
    location: Dict
    nearby_public_transport: Optional[str]

    @ dataclass
    class Settings:  # pylint: disable=too-few-public-methods
        source = StationModel
        projection = {
            "full_name": 1,
            "callsign": 1,
            "station_type": 1,
            "is_storage_available": 1,
            "is_charging_available": 1,
            "station_state": 1,
            "city_name": 1,
            "address": 1,
            "location": 1,
            "nearby_public_transport": 1
        }

    @ dataclass
    class Config:
        json_schema_extra = {
            "full_name": "Central Station",
            "callsign": "CENTRAL",
            "station_type": "Type A",
            "installed_lockers": 10,
            "station_state": "available",
            "is_storage_available": True,
            "is_charging_available": True,
            "city_name": "City",
            "address": "123 Main St",
            "location": {"lat": 40.7128, "lon": -74.0060},
            "nearby_public_transit": "Subway"
        }


try:
    for model in [StationModel, StationView]:
        model.model_json_schema()
except PydanticUserError as exc_info:
    assert exc_info.code == 'invalid-for-json-schema'
