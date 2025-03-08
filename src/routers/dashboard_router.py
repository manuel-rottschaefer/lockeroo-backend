"""
    This module contains the FastAPI router for handling reviews.
"""
# FastAPI
from fastapi import APIRouter, Depends
# Entities
from src.entities.user_entity import User
# Services
from src.services.dashboard_services import get_active_session_count
from src.services.exception_services import handle_exceptions
from src.services.auth_services import auth_check
from src.services.logging_services import logger_service as logger

# Create the router
dashboard_router = APIRouter()

### Session dashboard ###


@dashboard_router.get(
    '/active_session_count/', description='Get the amount of currently active sessions.')
@handle_exceptions(logger)
# @require_auth
async def active_session_count(
    user: User = Depends(auth_check)
) -> int:
    """Get the amount of all active sessions in the system."""
    return get_active_session_count(user)
