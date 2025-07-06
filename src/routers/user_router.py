"""
Lockeroo.station_router
-------------------------
This module provides endpoint routing for user functionalities

Key Features:
    - Provides various user endpoints

Dependencies:
    - fastapi
    - beanie
"""
# Basics
from typing import Optional, List
# FastAPI & Beanie
from fastapi import APIRouter, Depends, status
# Entities
from src.entities.user_entity import User
# Models
from lockeroo_models.session_models import SessionView, SessionConcludedView
from lockeroo_models.user_models import UserSummary
# Services
from src.services import user_services
from src.services.auth_services import auth_check
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger_service as logger

# Create the router
user_router = APIRouter()


@user_router.get(
    '/{user_id}',
    response_model=Optional[UserSummary],
    status_code=status.HTTP_200_OK,
    description='Get the details of a user.'
)
@handle_exceptions(logger)
async def get_user_details(
    user: User = Depends(auth_check),
) -> UserSummary:
    """Get the details of a user."""
    return await user_services.get_details(user=user)


@user_router.get(
    '/{user_id}/active_session',
    response_model=Optional[SessionView],
    status_code=status.HTTP_200_OK,
    description='Get the active session of a user, if any.'
)
@handle_exceptions(logger)
async def get_active_session(
    user: User = Depends(auth_check),
) -> SessionView:
    """Get the active session of a user, if any."""
    return await user_services.get_active_session(user=user)


@user_router.get(
    '/{user_id}/session_history',
    response_model=Optional[List[SessionConcludedView]],
    status_code=status.HTTP_200_OK,
    description='Get the session history of a user.'
)
@handle_exceptions(logger)
async def get_session_history(
    user: User = Depends(auth_check),
) -> List[SessionConcludedView]:
    """Get the session history of a user."""
    return await user_services.get_session_history(user=user)
