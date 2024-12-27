"""This module provides the Models for Station Maintenance events."""
# Types
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

# Beanie
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import View
from pydantic import Field, PydanticUserError

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

    started: Optional[datetime] = Field(
        None, description="Actual starting time")
    completed: Optional[datetime] = Field(
        None, description="Actual completion time")

    state: MaintenanceStates = Field(
        description="Current state of the maintenance item"
    )

    assigned_staff: ObjId = Field(None,
                                  description="The person assigned with this task")

    @ dataclass
    class Settings:  # pylint: disable=too-few-public-methods
        name = "maintenance"

    @ dataclass
    class Config:
        json_schema_extra = {
            "assigned_station": "60d5ec49f1d2b2a5d8f8b8b8",
            "scheduled_for": "2023-10-17T10:00:00",
            "planned_duration": "2:00:00",
            "state": "scheduled",
            "assigned_staff": "60d5ec49f1d2b2a5d8f8b8b8"
        }


try:
    MaintenanceModel.model_json_schema()
except PydanticUserError as exc_info:
    assert exc_info.code == 'invalid-for-json-schema'


class MaintenanceView(View):  # pylint: disable=too-many-ancestors
    """Entity of a station maintenance event"""
    id: str = Field(description="Unique identifier of the maintenance event.")

    assigned_station: str = Field(
        None, description="Station to which this maintenance is assigned to.")

    # Planned datetimes
    scheduled_for: datetime = Field(
        description="Scheduled time of maintenance")
    planned_duration: timedelta = Field(
        timedelta(hours=1), description="Planned duration of the maintenance session.")

    started: Optional[datetime] = Field(
        None, description="Actual starting time")
    completed: Optional[datetime] = Field(
        None, description="Actual completion time")

    state: MaintenanceStates = Field(
        description="Current state of the maintenance item"
    )

    assigned_staff: str = Field(
        None, description="The person assigned with this task")

    @ dataclass
    class Config:
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "assigned_station": "CENTRAL",
            "scheduled_for": "2023-10-17T10:00:00",
            "planned_duration": "2:00:00",
            "state": "scheduled",
            "assigned_staff": "John Doe"
        }
