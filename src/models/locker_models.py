"""
This module provides a model for the locker representation in the database
as well as other Enums and configurations.
"""
# Types
import dataclasses
from datetime import datetime, timedelta
from enum import Enum
# Basics
from typing import List, Optional

# Types
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import Update, View, after_event
from pydantic import BaseModel, Field

# Models
from src.models.station_models import StationModel
# Logging
from src.services.logging_services import logger


class LockerStates(str, Enum):
    """States of a locker."""
    LOCKED = 'locked'
    UNLOCKED = 'unlocked'


class LockerType(BaseModel):
    """Config representation of deployable locker types."""
    name: str = Field(description="Name of the locker type family."),
    description: str = Field("Well... a description.")
    stations: List[str] = Field(
        "List of station types at which this locker is installed."),
    dimensions: List[int] = Field(
        description="Physical dimensions in cm (x,y,z)."),
    payment_model: str = Field(description="Name of associated price model."),
    has_charging: bool = Field(
        description="Whether the lockers come with outlets."),
    maintenance_interval: timedelta = Field(
        description="Interval at which locker should be cleaned.")


class LockerModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a single locker in the database."""
    ### Identification ###
    id: Optional[ObjId] = Field(
        None, alias="_id", description='ObjectID in the database.')

    station: Link[StationModel] = Field(
        description='Station this locker belongs to.')

    pricing_model: str = Field(
        description="The pricing model assigned to this locker.")

    #### Locker Properties ###
    locker_type: str
    station_index: int = Field(
        ..., description='Index of the locker in the station (Also printed on the doors).')

    ### Operation State ###
    reported_state: LockerStates = Field(
        LockerStates.LOCKED, description='State of the locker as reported by the station.')

    ### Statistics ###
    total_session_count: int = Field(...,
                                     description='Total number of sessions.')
    total_session_duration: int = Field(...,
                                        description='Total duration of all sessions.')
    last_service_ts: datetime = Field(...,
                                      description='Timestamp of the last service.')

    @after_event(Update)
    def log_db_ops(self):
        """Log the Database operation for debugging purposes."""
        logger.debug(f"Locker '{self.id}' has been reported as {
                     self.reported_state}.")

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "lockers"


class LockerView(View):
    """A public view of the locker model."""

    id: Optional[ObjId] = Field(
        None, alias="_id", description='ObjectID in the database.')
    station: ObjId = Field(...,
                           description='Station this locker belongs to.')

    #### Locker Properties ###
    locker_type: str
    station_index: int = Field(
        ..., description='Index of the locker in the station (Also printed on the doors).')

    class Settings:  # pylint: disable=missing-class-docstring,too-few-public-methods
        source = LockerModel
