"""
Lockeroo.maintenance_services
-------------------------
This module provides endpoint handlers for maintenance management

Key Features:
    - Maintenance creation, scheduling, cancelling...

Dependencies:
    - fastapi
    - beanie
"""
# Types
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated
# FastApi and ODM
from fastapi import Path
from beanie import PydanticObjectId as ObjId
from beanie import SortDirection
# Entities
from src.entities.user_entity import User
from src.entities.station_entity import Station
from src.entities.maintenance_entity import Maintenance
# Models
from lockeroo_models.station_models import StationModel
from lockeroo_models.permission_models import PERMISSION
from lockeroo_models.maintenance_models import MaintenanceSessionModel, MaintenanceSessionState
# Servicies
from src.services.auth_services import permission_check
# Exceptions
from src.exceptions.maintenance_exceptions import InvalidMaintenanceSessionStateException


async def schedule(user: User, callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
                   staff_id: ObjId) -> Optional[MaintenanceSessionModel]:
    """Create a new maintenance event."""
    # 1: Verify permissions
    permission_check([PERMISSION.MAINTENANCE_MODIFY], user.doc.permissions)

    # 2; Get station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign
    )
    return await Maintenance().create(
        station_id=station.id,
        staff_id=staff_id)


async def cancel(
        user: User,
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        maint_id: ObjId) -> Optional[MaintenanceSessionModel]:
    """Cancel a maintenance event if it exists"""
    # 1: Verify permissions
    permission_check([PERMISSION.MAINTENANCE_MODIFY], user.doc.permissions)

    # 2: Try to find the maintenace event by its ID
    maint_inst: Optional[MaintenanceSessionModel] = await MaintenanceSessionModel.find(
        id=maint_id,
        callsign=callsign
    )
    if maint_inst is None:
        return None

    # 3: Check whether the maintenance event is scheduled
    if maint_inst.state != MaintenanceSessionState.SCHEDULED:
        raise InvalidMaintenanceSessionStateException(
            maintenance_id=maint_id,
            expected_state=MaintenanceSessionState.SCHEDULED,
            actual_state=maint_inst.state
        )

    # 4: Cancel the maintenance event
    maint_inst.state = MaintenanceSessionState.CANCELED
    await maint_inst.save_changes()
    return maint_inst


async def complete(
        user: User,
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        maint_id: ObjId) -> Optional[MaintenanceSessionModel]:
    """Cancel a maintenance event if it exists"""
    # 1: Verify permissions
    permission_check([PERMISSION.MAINTENANCE_MODIFY], user.doc.permissions)

    # 2: Try to find the maintenace event by its ID
    maint_evnt: Optional[MaintenanceSessionModel] = await MaintenanceSessionModel.find(
        id=maint_id,
        callsign=callsign
    )
    if maint_evnt is None:
        return None

    # 3: Check whether the maintenance event is active
    if maint_evnt.state != MaintenanceSessionState.ACTIVE:
        raise InvalidMaintenanceSessionStateException(
            maintenance_id=maint_id,
            expected_state=MaintenanceSessionState.ACTIVE,
            actual_state=maint_evnt.state
        )

    # 4: Complete the maintenance event
    maint_evnt.state = MaintenanceSessionState.COMPLETED
    await maint_evnt.save_changes()
    return maint_evnt


async def get_next(
        user: User,
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')]) -> Optional[MaintenanceSessionModel]:
    """Get the next scheduled maintenance event at the station."""
    # 1: Verify permissions
    permission_check([PERMISSION.MAINTENANCE_MODIFY], user.doc.permissions)

    # 1: Find the station by its callsign
    return await MaintenanceSessionModel.find(
        MaintenanceSessionModel.assigned_station.callsign == callsign,  # pylint: disable=no-member
        MaintenanceSessionModel.state == MaintenanceSessionState.SCHEDULED
    ).sort((MaintenanceSessionModel.scheduled_for, SortDirection.DESCENDING)).first_or_none()


async def has_scheduled(user: User, station_id: ObjId) -> bool:
    """Check whether the given station has a maintenance scheduled in the next three hours."""
    # 1: Verify permissions
    permission_check([PERMISSION.MAINTENANCE_MODIFY], user.doc.permissions)

    # 2: Check if there are any active maintenance event at this station
    active_maintenance: MaintenanceSessionModel = await MaintenanceSessionModel.find_one(
        MaintenanceSessionModel.assigned_station == station_id,
        MaintenanceSessionModel.state == MaintenanceSessionState.ACTIVE)

    # Get current time
    now = datetime.now(timezone.utc)
    in_three_hours = now + timedelta(hours=3)
    scheduled_maintenance: MaintenanceSessionModel = await MaintenanceSessionModel.find_one(
        MaintenanceSessionModel.scheduled_for < in_three_hours)

    return active_maintenance is not None or scheduled_maintenance is not None
