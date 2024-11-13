"""
    This module contains the FastAPI router for handling reviews.
"""
# Basics
from typing import Annotated

# Database utils
from beanie import PydanticObjectId as ObjId

# FastAPI
from fastapi import APIRouter, Path,

# Auth
from fief_client import FiefAccessTokenInfo

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
        access_info: FiefAccessTokenInfo = None,) -> MaintenanceModel:
    """Get the availability of lockers at the station"""
    return await maintenance_services.create(
        call_sign=call_sign, _staff_id=access_info['id']
    )


@maintenance_router.get('/{call_sign}/maintenance/next',
                        response_model=MaintenanceModel)
@handle_exceptions(logger)
@require_auth
async def get_next_scheduled_maintenance(
    call_sign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
    access_info: FiefAccessTokenInfo = None
) -> MaintenanceModel:
    """Get the availability of lockers at the station"""
    return await maintenance_services.get_next(
        call_sign=call_sign,
        user_id=access_info['id']
    )
