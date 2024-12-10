"""
    This module contains the FastAPI router for handling admin requests.
"""
# Basics
import os

# FastAPI
from fastapi import APIRouter

from src.services.database_services import restore_mongodb_data
# Services
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger

# Create the router
admin_router = APIRouter()


@admin_router.get('/reset',
                  description='Reset the database and populate it with mock data')
@handle_exceptions(logger)
async def reset_db():
    """Reset the db"""
    logger.info('Resetting the database.')
    #await restore_mongodb_data(os.getenv('MONGO_DUMP'))