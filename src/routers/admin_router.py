"""
    This module contains the FastAPI router for handling admin requests.
"""
# Basics
import os

# FastAPI
from fastapi import APIRouter

from src.services.database_services import restore_json_mock_data
# Services
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger_service as logger

# Create the router
admin_router = APIRouter()


@admin_router.get(
    '/reset',
    description='Reset the database and populate it with mock data')
@ handle_exceptions(logger)
async def reset_db():
    """Reset the db"""
    await restore_json_mock_data(os.getenv('MONGO_DATA'))
