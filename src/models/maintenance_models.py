"""This module provides the Models for Station Maintenance events."""
# Types
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

# Beanie
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from pydantic import Field

# Models
from src.models.station_models import StationModel


class MaintenanceStates(str, Enum):
    """All possible states of a station maintenance event"""
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    COMPLETED = "completed"
    ISSUE = "issue"
    CANCELED = "canceled"


class MaintenanceModel(Document):  # pylint: disable=too-many-ancestors
    """Entity of a station maintenance event"""

    id: ObjId = Field(None, alias="_id")

    assigned_station: Link[StationModel] = Field(
        None, description="Station to which this maintenance is assigned to.")

    # Planned datetimes
    scheduled_for: datetime = Field(
        description="Scheduled time of maintenance")
    planned_duration: timedelta = Field(
        timedelta(hours=1), description="Planned duration of the maintenance session.")

    started: Optional[datetime] = Field(description="Actual starting time")
    completed: Optional[datetime] = Field(
        description="Actual completion time")

    state: MaintenanceStates = Field(
        description="Current state of the maintenance item"
    )

    assigned_staff: ObjId = Field(None,
                                  description="The person assigned with this task")

    class Settings:  # pylint: disable=missing-class-docstring, too-few-public-methods
        name = "maintenance"
