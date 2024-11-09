"""
Locker Models
"""

# Types
import dataclasses

# Basics
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

# Types
from beanie import Document, Replace, after_event
from beanie import PydanticObjectId as ObjId

# Models
from pydantic import BaseModel, Field

# Logging
from src.services.logging_services import logger


class LockerStates(str, Enum):
    """States of a locker"""
    LOCKED = 'locked'
    UNLOCKED = 'unlocked'


class LockerTypes(str, Enum):
    """Types of lockers"""
    SMALL = 'small'
    MEDIUM = 'medium'
    LARGE = 'large'


class PricingModel(BaseModel):
    """Pricing Models for Lockers"""
    basePrice: int                  # Minimum price for a session
    # Price per minute after base period (ct)
    minuteRate: float
    maxPrice: int                   # Maximum price to pay, after that locker is emptied


class LockerType(BaseModel):
    """Locker Type / Version"""
    name: str                       # Name of the Type of Locker
    description: str                # Examples of Luggage or other suitable items
    size: Tuple[int, int, int]      # Physical size of the locker
    render: Optional[str] = None    # Render image for UI
    pricing: PricingModel           # Reference to the pricing model


class LockerModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a single locker in the database"""
    ### Identification ###
    id: Optional[ObjId] = Field(
        None, alias="_id", description='ObjectID in the database')
    parent_station: ObjId = Field(...,
                                  description='Station this locker belongs to')

    #### Locker Properties ###
    locker_type: LockerType
    station_index: int = Field(
        ..., description='Index of the locker in the station (Also printed on the doors)')

    ### Operation State ###
    reported_state: LockerStates = Field(
        LockerStates.LOCKED, description='State of the locker as reported by the station')

    ### Statistics ###
    total_session_count: int = Field(...,
                                     description='Total number of sessions')
    total_session_duration: int = Field(...,
                                        description='Total duration of all sessions')
    last_service_ts: datetime = Field(...,
                                      description='Timestamp of the last service')

    @after_event(Replace)
    def log_db_ops(self):
        """Log the Database operation for debugging purposes."""
        logger.debug(f"Locker {self.id} is has been reported as '{
                     self.reported_state}'.")

    @dataclasses.dataclass
    class Settings:
        """Name in database"""
        name = "lockers"
