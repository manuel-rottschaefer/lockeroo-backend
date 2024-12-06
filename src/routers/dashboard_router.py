"""
    This module contains the FastAPI router for handling reviews.
"""

# FastAPI
from fastapi import APIRouter
# Auth
from fief_client import FiefAccessTokenInfo

# Beanie
from beanie.operators import In

# Models
from src.models.session_models import SessionModel, ACTIVE_SESSION_STATES
# Services
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger

# Create the router
dashboard_router = APIRouter()

### Session dashboard ###


@dashboard_router.get('/active_session_count/')
@handle_exceptions(logger)
# @require_auth
async def get_active_session_count(
    _access_info: FiefAccessTokenInfo = None
) -> int:
    """Get the amount of currently active sessions."""
    return await SessionModel.find(
        In(SessionModel.session_state, ACTIVE_SESSION_STATES),
    ).to_list()
