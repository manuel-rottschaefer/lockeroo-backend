"""Provides utility functions for the maintenance management backend."""
# Types
from datetime import datetime, timedelta
from typing import Optional, Annotated
# FastApi and ODM
from fastapi import Path
from beanie import PydanticObjectId as ObjId
from beanie import SortDirection
# Entities
from src.entities.station_entity import Station
from src.entities.maintenance_entity import Maintenance
# Models
from src.models.station_models import StationModel
from src.models.maintenance_models import MaintenanceModel, MaintenanceState
# Exceptions
from src.exceptions.maintenance_exceptions import InvalidMaintenanceStateException


async def schedule(callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
                   staff_id: ObjId) -> Optional[MaintenanceModel]:
    """Create a new maintenance event."""
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign
    )
    return await Maintenance().create(
        station_id=station.id,
        staff_id=staff_id)


async def cancel(
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        maint_id: ObjId) -> Optional[MaintenanceModel]:
    """Cancel a maintenance event if it exists"""
    # 1: Try to find the maintenace event by its ID
    maint_inst: Optional[MaintenanceModel] = await MaintenanceModel.find(
        id=maint_id,
        callsign=callsign
    )
    if maint_inst is None:
        return None

    # 2: Check whether the maintenance event is scheduled
    if maint_inst.state != MaintenanceState.SCHEDULED:
        raise InvalidMaintenanceStateException(
            maintenance_id=maint_id,
            expected_state=MaintenanceState.SCHEDULED,
            actual_state=maint_inst.state
        )

    # 3 Cancel the maintenance event
    maint_inst.state = MaintenanceState.CANCELED
    await maint_inst.save_changes()
    return maint_inst


async def complete(
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        maint_id: ObjId) -> Optional[MaintenanceModel]:
    """Cancel a maintenance event if it exists"""
    # 1: Try to find the maintenace event by its ID
    maint_inst: Optional[MaintenanceModel] = await MaintenanceModel.find(
        id=maint_id,
        callsign=callsign
    )
    if maint_inst is None:
        return None

    # 2: Check whether the maintenance event is active
    if maint_inst.state != MaintenanceState.ACTIVE:
        raise InvalidMaintenanceStateException(
            maintenance_id=maint_id,
            expected_state=MaintenanceState.ACTIVE,
            actual_state=maint_inst.state
        )

    # 3: Complete the maintenance event
    maint_inst.state = MaintenanceState.COMPLETED
    await maint_inst.save_changes()
    return maint_inst


async def get_next(
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')]) -> Optional[MaintenanceModel]:
    """Get the next scheduled maintenance event at the station."""
    # 1: Find the station by its callsign
    return await MaintenanceModel.find(
        MaintenanceModel.assigned_station.callsign == callsign,  # pylint: disable=no-member
        MaintenanceModel.state == MaintenanceState.SCHEDULED
    ).sort((MaintenanceModel.scheduled_for, SortDirection.DESCENDING)).first_or_none()


async def has_scheduled(station_id: ObjId) -> bool:
    """Check whether the given station has a maintenance scheduled in the next three hours."""
    # 1: Check if there are any active maintenance event at this station
    active_maintenance: MaintenanceModel = await MaintenanceModel.find_one(
        MaintenanceModel.assigned_station == station_id,
        MaintenanceModel.state == MaintenanceState.ACTIVE
    )

    now = datetime.now()
    in_three_hours = now + timedelta(hours=3)
    scheduled_maintenance: MaintenanceModel = await MaintenanceModel.find_one(
        MaintenanceModel.scheduled_for < in_three_hours
    )

    return active_maintenance is not None or scheduled_maintenance is not None
