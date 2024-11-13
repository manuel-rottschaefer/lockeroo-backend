"""
    This module contains the FastAPI router for handling reviews.
"""
# Basics

# Database utils
from beanie.operators import NotIn

# FastAPI
from fastapi import APIRouter

# Auth
from fief_client import FiefAccessTokenInfo

# Models
from src.models.session_models import SessionModel, INACTIVE_SESSION_STATES

# Services
from src.services.exceptions import handle_exceptions
from src.services.logging_services import logger
from src.services.auth_services import require_auth

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
        NotIn(SessionModel.session_state, INACTIVE_SESSION_STATES)
    ).count()
