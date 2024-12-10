"""Provides utility functions for the maintenance management backend."""

# Typing
from datetime import datetime, timedelta
from typing import Optional

# ObjectID handling
from beanie import PydanticObjectId as ObjId
from beanie import SortDirection

# Models
from src.models.maintenance_models import MaintenanceModel, MaintenanceStates


async def get_next(station_id: ObjId) -> Optional[MaintenanceModel]:
    """Creates a new maintenance event."""
    return await MaintenanceModel.find(
        MaintenanceModel.assigned_station == station_id,
        MaintenanceModel.state == MaintenanceStates.SCHEDULED
    ).sort((MaintenanceModel.scheduled_for, SortDirection.DESCENDING)).first_or_none()


async def has_scheduled(station_id: ObjId) -> bool:
    """Check whether the given station has a maintenance scheduled in the next three hours."""
    # 1: Check if there are any active maintenance event at this station
    active_maintenance: MaintenanceModel = await MaintenanceModel.find_one(
        MaintenanceModel.assigned_station == station_id,
        MaintenanceModel.state == MaintenanceStates.ACTIVE
    )

    now = datetime.now()
    in_three_hours = now + timedelta(hours=3)
    scheduled_maintenance: MaintenanceModel = await MaintenanceModel.find_one(
        MaintenanceModel.scheduled_for < in_three_hours
    )

    return active_maintenance is not None or scheduled_maintenance is not None
