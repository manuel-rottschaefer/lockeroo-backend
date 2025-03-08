"""
    This module contains the FastAPI router for handling admin requests.
"""
# Basics
import os
# FastAPI
from fastapi import APIRouter, Depends
# Models
from src.models.permission_models import PERMISSION
# Services
from src.services.exception_services import handle_exceptions
from src.services.database_services import restore_json_mock_data
from src.services.logging_services import logger_service as logger
from src.services.auth_services import auth_check, permission_check
# Entities
from src.entities.user_entity import User

# Create the router
admin_router = APIRouter()


@admin_router.get(
    '/reset', description='Reset the database and populate it with mock data')
@handle_exceptions(logger)
async def reset_db(
    user: User = Depends(auth_check)
):
    """Reset the db"""
    # 1: Check for permissions
    permission_check([PERMISSION.FIEF_ADMIN], user.doc.permissions)
    await restore_json_mock_data(os.getenv('MONGO_DATA'))
