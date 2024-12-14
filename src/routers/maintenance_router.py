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
from src.services import maintenance_services
from src.services.auth_services import require_auth
# Services
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger

# Create the router
maintenance_router = APIRouter()


@maintenance_router.post('/{callsign}/maintenance/schedule',
                         response_model=MaintenanceModel)
@handle_exceptions(logger)
@require_auth
async def create_scheduled_maintenance(
        callsign:  Annotated[str, Path(pattern='^[A-Z]{6}$')],
        staff_id: str,
        _access_info: FiefAccessTokenInfo = None,) -> MaintenanceModel:
    """Get the availability of lockers at the station"""
    station: Station = await Station().find(callsign=callsign)

    maintenance_item = await Maintenance().create(station_id=station.id,
                                                  staff_id=staff_id)
    return maintenance_item.document


@maintenance_router.get('/{callsign}/maintenance/next',
                        response_model=MaintenanceModel)
@handle_exceptions(logger)
@require_auth
async def get_next_scheduled_maintenance(
    callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
    _access_info: FiefAccessTokenInfo = None
) -> MaintenanceModel:
    """Get the availability of lockers at the station"""
    station: Station = await Station().find(callsign=callsign)
    return await maintenance_services.get_next(
        station_id=station.id
    )
