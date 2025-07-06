"""
Lockeroo.task_services
-------------------------
This module provides user management utilities

Key Features:
    - Provides various user endpoint handlers
    
Dependencies:
    - beanie
"""
# Basics
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from uuid import UUID
# Beanie
from beanie import PydanticObjectId as ObjId, SortDirection
from beanie.operators import In
# Entities
from src.entities.user_entity import User
# Exceptions
from src.exceptions.user_exceptions import UserHasActiveSessionException
# Models
from lockeroo_models.user_models import UserSummary
from lockeroo_models.session_models import (
    SessionModel,
    SessionView,
    SessionConcludedView,
    SessionState,
    ACTIVE_SESSION_STATES)


async def get_details(user: User) -> Optional[UserSummary]:
    """Get the details of a user."""
    return UserSummary(**user.doc.model_dump(include=UserSummary.model_fields.keys()))
    # return await UserModel.find(
    #    UserModel.fief_id == UUID(user.doc.fief_id)).project(UserSummary).first_or_none()


async def has_active_session(user: User) -> bool:
    """Check if the given user has an active session"""

    active_session = await SessionModel.find(
        SessionModel.assigned_user.fief_id == user.fief_id,  # pylint: disable=no-member
        In(SessionModel.session_state,
           ACTIVE_SESSION_STATES),  # pylint: disable=no-member
        fetch_links=True
    ).sort((SessionModel.created_at, SortDirection.DESCENDING)).first_or_none()

    if active_session:
        raise UserHasActiveSessionException(user_id=user.fief_id)

    return active_session is not None


async def get_active_session(user: User) -> Optional[SessionView]:
    """Return the active session of a user, if any."""
    return await SessionModel.find(
        SessionModel.assigned_user.fief_id == user.fief_id,  # pylint: disable=no-member
        In(SessionModel.session_state,
           ACTIVE_SESSION_STATES),  # pylint: disable=no-member
        fetch_links=True
    ).sort(
        (SessionModel.created_at, SortDirection.DESCENDING)
    ).project(SessionView).first_or_none()


async def get_session_history(user: User) -> List[SessionConcludedView]:
    """Return the session history of a user."""
    return await SessionModel.find(
        SessionModel.assigned_user.fief_id == user.fief_id,  # pylint: disable=no-member
        fetch_links=True).sort(
        (SessionModel.created_at, SortDirection.DESCENDING)
    ).project(SessionConcludedView).to_list()


async def get_expired_session_count(user_id: ObjId) -> int:
    return await SessionModel.find(
        SessionModel.assigned_user.id == user_id,  # pylint: disable=no-member
        SessionModel.session_state == SessionState.EXPIRED,
        SessionModel.created_at >= (datetime.now(
            timezone.utc) - timedelta(hours=24)),
        fetch_links=True
    ).count()
