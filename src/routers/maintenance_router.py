"""
    This module contains the FastAPI router for handling reviews.
"""
# Basics
from typing import Annotated

# FastAPI
from fastapi import APIRouter, Path

# Auth
from fief_client import FiefAccessTokenInfo

# Entities
from src.entities.maintenance_entity import Maintenance
from src.entities.station_entity import Station

# Models
from src.models.maintenance_models import MaintenanceModel

# Services
from src.services.exceptions import handle_exceptions
from src.services.logging_services import logger
from src.services.auth_services import require_auth
from src.services import maintenance_services

# Create the router
maintenance_router = APIRouter()


@maintenance_router.post('/{call_sign}/maintenance/schedule',
                         response_model=MaintenanceModel)
@handle_exceptions(logger)
@require_auth
async def create_scheduled_maintenance(
        call_sign:  Annotated[str, Path(pattern='^[A-Z]{6}$')],
        staff_id: str,
        _access_info: FiefAccessTokenInfo = None,) -> MaintenanceModel:
    """Get the availability of lockers at the station"""
    station: Station = await Station().fetch(call_sign=call_sign)

    maintenance_item = await Maintenance().create(station_id=station.id,
                                                  staff_id=staff_id)
    return maintenance_item.document


@maintenance_router.get('/{call_sign}/maintenance/next',
                        response_model=MaintenanceModel)
@handle_exceptions(logger)
@require_auth
async def get_next_scheduled_maintenance(
    call_sign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
    _access_info: FiefAccessTokenInfo = None
) -> MaintenanceModel:
    """Get the availability of lockers at the station"""
    station: Station = await Station().fetch(call_sign=call_sign)
    return await maintenance_services.get_next(
        station_id=station.id
    )
