"""
This module provides a model for the locker representation in the database
as well as other Enums and configurations.
"""
# Types
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

# Config
import yaml
# Beanie
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import SaveChanges, View, after_event
from pydantic import BaseModel, Field, PydanticUserError

# Models
from src.models.station_models import StationModel
# Services
# Logging
from src.services.logging_services import logger_service as logger


class LockerState(str, Enum):
    """Lock State of a locker."""
    LOCKED = 'locked'
    UNLOCKED = 'unlocked'
    STALE = 'stale'


class LockerAvailability(str, Enum):
    """Availability of a locker."""
    OPERATIONAL = 'operational'
    MAINTENANCE = 'maintenance'
    OUT_OF_ORDER = 'out_of_order'


class LockerType(BaseModel):
    """Config representation of deployable locker types."""
    name: str = Field(description="Name of the locker type family.")
    description: str = Field("Well... a description.")
    dimensions: List[int] = Field(
        description="Physical dimensions in cm (x,y,z).")
    pricing_model: str = Field(description="Name of associated price model.")
    has_outlet: bool = Field(
        description="Whether the lockers come with outlets.")
    maintenance_interval: timedelta = Field(
        description="Interval at which locker should be cleaned.")


class LockerModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a single locker in the database."""
    ### Identification ###
    id: ObjId = Field(None, alias="_id")

    station: Link[StationModel] = Field(
        description='Station this locker belongs to.')

    callsign: str = Field(
        None, description="Call sign of the locker in the format STATION_CALLSIGN#station_index.")

    #### Locker Properties ###
    locker_type: LockerType = Field(None, description='Type of the locker.')
    station_index: int = Field(
        ..., description='Index of the locker in the station (Also printed on the doors).')

    ### States ###
    availability: LockerAvailability = Field(
        LockerAvailability.OPERATIONAL, description='Availability of the locker.')

    reported_state: LockerState = Field(
        LockerState.LOCKED, description='State of the locker as reported by the station.')

    ### Statistics ###
    total_session_count: int = Field(...,
                                     description='Total number of sessions.')
    total_session_duration: timedelta = Field(...,
                                              description='Total duration of all sessions.')
    last_service_at: datetime = Field(...,
                                      description='Timestamp of the last service.')

    @ after_event(SaveChanges)
    def log_changes(self):
        """Log the Database operation for debugging purposes."""
        logger.debug(f"Locker '#{self.callsign}' has been registered as {
                     self.reported_state}.")

    @ dataclass
    class Settings:
        name = "lockers"
        use_state_management = True

    @ dataclass
    class Config:
        json_schema_extra = {
            "station": "60d5ec49f1d2b2a5d8f8b8b8",
            "callsign": "CENTRAL#1",
            "pricing_model": "Standard",
            "locker_type": {
                "name": "Type A",
                "description": "A small locker for small items.",
                "dimensions": [30, 30, 30],
                "pricing_model": "Standard",
                "has_outlet": False,
                "maintenance_interval": "7 days"
            },
            "station_index": 1,
            "reported_state": "locked",
            "total_session_count": 50,
            "total_session_duration": "100:00:00",
            "last_service_at": "2023-09-10T10:00:00"
        }


class LockerView(View):
    """A public view of the locker model."""
    station: str
    locker_type: str
    availability: str
    station_index: int

    class Settings:  # pylint: disable=too-few-public-methods
        source = LockerModel
        projection = {
            "station": "$station.callsign",
            "locker_type": "$locker_type",
            "availability": {"$toString": "$availability"},
            "station_index": "$station_index"
        }

    @ dataclass
    class Config:
        json_schema_extra = {
            "station": "CENTRAL",
            "locker_type": "Type A",
            "availability": "operational",
            "station_index": 1
        }


class ReducedLockerView(View):  # Internal use only
    """Only id and name of the locker type."""
    locker_type: str
    locker_state: str

    class Settings:  # pylint: disable=too-few-public-methods
        source = LockerModel
        projection = {
            "locker_type": "$locker_type.name",
            "locker_state": {"$toString": "$reported_state"}
        }

    @ dataclass
    class Config:
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "locker_type": "Medium",
            "locker_state": "locked"
        }


class LockerTypeAvailabilityView(View):
    """Representation of the availability of a locker type at a station."""
    issued_at: datetime
    station: str
    locker_type: str
    is_available: bool


def load_locker_types(config_path: str) -> Optional[List[LockerType]]:
    """Load locker types from configuration file."""
    locker_types: List[LockerType] = []
    try:
        with open(config_path, 'r', encoding='utf-8') as cfg:
            type_dicts = yaml.safe_load(cfg)
            locker_types.extend(LockerType(name=name, **details)
                                for name, details in type_dicts.items())
        return locker_types
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {config_path}.")
        return None
    except yaml.YAMLError as e:
        logger.warning(f"Error parsing YAML configuration: {e}")
        return None
    except TypeError as e:
        logger.warning(f"Data structure mismatch: {e}")
        return None


# Load locker types from configuration
LOCKER_TYPES: List[LockerType] = load_locker_types(
    config_path='src/config/locker_types.yml')
LOCKER_TYPE_NAMES = [locker.name for locker in LOCKER_TYPES]


try:
    models = [LockerModel,
              LockerView,
              ReducedLockerView,
              LockerTypeAvailabilityView]
    for model in models:
        model.model_json_schema()
except PydanticUserError as exc_info:
    assert exc_info.code == 'invalid-for-json-schema'
