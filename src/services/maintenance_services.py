"""Provides utility functions for the maintenance management backend."""

# Typing
from typing import List, Optional
from uuid import UUID

# ObjectID handling
from beanie import PydanticObjectId as ObjId

# FastAPI utilities
from fastapi import HTTPException

# Entities
from src.entities.maintenance_entity import Maintenance
from src.entities.station_entity import Station

# Models
from src.models.maintenance_models import MaintenanceModel, MaintenanceStates


# Services
from .logging_services import logger
from .exceptions import ServiceExceptions


async def create(call_sign: str,
                 _staff_id: str) -> MaintenanceModel:
    """Creates a new maintenance event."""
    station: Station = await Station().fetch(call_sign=call_sign)
    # TODO: Raise 404 here
    maintenance = await Maintenance().create(station_id=station.id, staff_id=None)
    return maintenance.document


async def get_next(call_sign: str) -> Optional[MaintenanceModel]:
    """Creates a new maintenance event."""
    station: Station = await Station().fetch(call_sign=call_sign)
    # TODO: Raise 404 here

    return await MaintenanceModel.find(
        MaintenanceModel.assigned_station == station.id,
        MaintenanceModel.state == MaintenanceStates.SCHEDULED
    ).sort(MaintenanceModel.scheduled).first_or_none()
