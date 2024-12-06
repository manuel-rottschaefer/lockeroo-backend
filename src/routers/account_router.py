"""
This file contains the router for the user related endpoints
"""

# Types
from typing import List
from uuid import UUID

# FastAPI
from fastapi import APIRouter, HTTPException

from src.models.user_models import UserSummary
# Models
from src.models.session_models import SessionModel, SessionView
from src.models.account_models import AccountSummary

# Services
from src.services.exceptions import ServiceExceptions

# Initialize the router
account_router = APIRouter()


@user_router.get('/{user_id}/history',
                 response_model=List[SessionView],
                 description='Get a list of sessions from a user')
async def get_user_session_history(user_id: UUID, count: int = 100):
    """Get a list of completed sessions of this user"""
    # Get station data from the database
    session_list = await SessionModel.find(
        SessionModel.user.id == user_id,  # pylint: disable=no-member
        fetch_links=True
    ).limit(count).sort(SessionModel.created_ts).to_list(count)

    if not session_list:
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.SESSION_NOT_FOUND.value)

    return session_list


@user_router.get('/summary',
                 response_model=UserSummary,
                 description='Get a quick summary of the user activity')
async def get_user_summary(_user_id: str):
    """Return user summary"""
    return None
