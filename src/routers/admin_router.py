"""
    This module contains the FastAPI router for handling admin requests.
"""
# Basics
import os

# FastAPI
from fastapi import APIRouter

# Services
from src.services.exceptions import handle_exceptions
from src.services.database_services import restore_mock_data
from src.services.logging_services import logger

# Create the router
admin_router = APIRouter()

# TODO: Reset station queue endpoint


@admin_router.get('/reset',
                  description='Reset the database and populate it with mock data')
@handle_exceptions(logger)
async def reset_db():
    """Reset the db"""
    return await restore_mock_data(os.getenv('MOCK_LOC'))
