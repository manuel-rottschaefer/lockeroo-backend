"""
This file contains the router for the account related endpoints
"""

# Types
from typing import List
from uuid import UUID

# FastAPI
from fastapi import APIRouter, HTTPException

# Models
from src.models.session_models import SessionModel, SessionView
from src.models.account_models import AccountSummary

# Services
from src.services.exceptions import ServiceExceptions

# Initialize the router
account_router = APIRouter()


@account_router.get('/{account_id}/history',
                    response_model=List[SessionView],
                    description='Get a list of sessions from a user')
async def get_account_history(account_id: UUID, count: int = 100):
    """Get a list of completed sessions of this account"""
    # Get station data from the database
    session_list = await SessionModel.find(
        SessionModel.assigned_account == UUID(account_id)
    ).limit(count).sort(SessionModel.created_ts).to_list(count)

    if not session_list:
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.SESSION_NOT_FOUND.value)

    return session_list


@account_router.get('/summary',
                    response_model=AccountSummary,
                    description='Get a quick summary of the user activity')
async def get_account_summary(_account_id: UUID):
    """Return account summary"""
    return None
