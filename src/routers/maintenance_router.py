"""
    This module contains the FastAPI router for handling reviews.
"""
# Basics
from typing import Annotated
# FastAPI
from fastapi import APIRouter, Path, status, Depends
# Entities
from src.entities.user_entity import User
# Models
from src.models.maintenance_models import MaintenanceView
from src.services import maintenance_services
from src.services.auth_services import auth_check
# Services
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger_service as logger

# Create the router
maintenance_router = APIRouter()


@maintenance_router.get(
    '/{callsign}/next',
    description="Get the next scheduled maintenance for a given station.",
    tags=['maintenance'],
    status_code=status.HTTP_200_OK,
    response_model=MaintenanceView)
@handle_exceptions(logger)
async def get_next_scheduled_maintenance(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$',
        description="The callsign of the station of interest.")],
    user: User = Depends(auth_check)
) -> MaintenanceView:
    """Get the next scheduled maintenance for a given station."""
    return await maintenance_services.get_next(
        user=user,
        callsign=callsign)


@maintenance_router.patch(
    '/{callsign}/schedule',
    description="Schedule a maintenance for a given station and staff ID.",
    tags=['maintenance'],
    status_code=status.HTTP_201_CREATED,
    response_model=MaintenanceView,
)
@handle_exceptions(logger)
async def request_maintenance_scheduling(
    callsign:  Annotated[str, Path(
        pattern='^[A-Z]{6}$',
        description="The callsign of the station at which the maintenace is supposed to happen.")],
    staff_id: Annotated[str, Path(
        pattern='^[0-9]+$',
        description="The ID of the staff member who is supposed to perform the maintenance.")],
    user: User = Depends(auth_check)
) -> MaintenanceView:
    """Create a new scheduled maintenance for a given station and staff ID."""
    return await maintenance_services.schedule(
        user=user,
        callsign=callsign,
        staff_id=staff_id)


@maintenance_router.put(
    '/{callsign}/cancel',
    description="Cancel a scheduled maintenance for a given station.",
    tags=['maintenance'],
    status_code=status.HTTP_200_OK,
    response_model=MaintenanceView)
@handle_exceptions(logger)
async def request_maintenance_cancelation(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$',
        description="The callsign of the station at which the maintenace is supposed to happen.")],
    maintenance_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$',
        description="The unique identifier of the maintenance to be canceled.")],
    user: User = Depends(auth_check)
) -> MaintenanceView:
    """Complete a scheduled maintenance for a given station."""
    return await maintenance_services.cancel(
        user=user,
        callsign=callsign,
        maint_id=maintenance_id
    )


@maintenance_router.put(
    '/{callsign}/complete',
    description="Complete a scheduled maintenance for a given station.",
    tags=['maintenance'],
    status_code=status.HTTP_200_OK,
    response_model=MaintenanceView)
@handle_exceptions(logger)
async def request_maintenance_completement(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$',
        description="The callsign of the station at which the maintenace is supposed to happen.")],
    maintenance_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$',
        description="The unique identifier of the maintenance to be completed.")],
    _comment: str,
    user: User = Depends(auth_check)
) -> MaintenanceView:
    """Complete a scheduled maintenance for a given station."""
    return await maintenance_services.complete(
        user=user,
        callsign=callsign,
        maint_id=maintenance_id
    )
