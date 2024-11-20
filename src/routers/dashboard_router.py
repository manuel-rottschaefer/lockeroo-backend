"""
    This module contains the FastAPI router for handling reviews.
"""

# FastAPI
from fastapi import APIRouter

# Auth
from fief_client import FiefAccessTokenInfo

# Models
from src.models.session_models import SessionModel

# Services
from src.services.exceptions import handle_exceptions
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
    return await SessionModel.aggregate([
        {
            "$match": {
                "session_state.is_active": True  # Match documents where the second element is True
            }
        },
    ]).count()
