"""
This module provides a model for the locker representation in the database
as well as other Enums and configurations.
"""
# Types
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, timedelta
from enum import Enum
# Config
import yaml
# Beanie
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import SaveChanges, View, after_event
from pydantic import BaseModel, Field
# Models
from src.models.station_models import StationModel
# Services
# Logging
from src.services.logging_services import logger


class LockerState(str, Enum):
    """Lock State of a locker."""
    LOCKED = 'locked'
    UNLOCKED = 'unlocked'


class LockerAvailability(str, Enum):
    """Availability of a locker."""
    OPERATIONAL = 'operational'
    MAINENANCE = 'maintenance'
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
    id: ObjId = Field(
        None, alias="_id", description='ObjectID in the database.')
    station: str = Field(None,
                         description='Station callsign this locker belongs to.')

    #### Locker Properties ###
    locker_type: str
    station_index: int = Field(
        ..., description='Index of the locker in the station.')

    class Settings:  # pylint: disable=too-few-public-methods
        source = LockerModel
        projection = {
            "id": "$_id",
            "station": "$station.callsign",
            "locker_type": "$locker_type",
            "station_index": "$station_index"
        }

    @ dataclass
    class Config:
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "station": "CENTRAL",
            "locker_type": "Type A",
            "station_index": 1
        }


class LockerTypeAvailability(BaseModel):
    """Representation of the availability of a locker type at a station."""
    locker_type: str = Field(description="Name of the locker type.")
    station: str = Field(description="Name of the station.")
    total_count: int = Field(description="Total number of lockers.")
    is_available: bool = Field(
        description="Whether the locker type is currently available at the station.")


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
    except yaml.YAMLError as e:
        logger.warning(f"Error parsing YAML configuration: {e}")
    except TypeError as e:
        logger.warning(f"Data structure mismatch: {e}")


LOCKER_TYPES: List[LockerType] = load_locker_types(
    config_path='src/config/locker_types.yml')
