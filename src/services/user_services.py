"""Provides utility functions for the the user management backend."""
# Types
from typing import Optional, List
from datetime import datetime, timedelta
from uuid import UUID
# Beanie
from beanie import PydanticObjectId as ObjId, SortDirection
from beanie.operators import In
# Exceptions
from src.exceptions.user_exceptions import UserHasActiveSessionException
# Models
from src.models.user_models import UserModel, UserSummary, UserQuickStats
from src.models.session_models import (
    SessionModel,
    SessionView,
    SessionState,
    ACTIVE_SESSION_STATES)


async def get_details(user_id: ObjId) -> Optional[UserSummary]:
    """Get the details of a user."""
    return await UserModel.get(
        user_id).project(UserSummary).first_or_none()


async def get_quick_stats(user_id: ObjId) -> UserQuickStats:
    """Get the quick stats of a user."""
    return await UserModel.get(
        user_id).project(UserQuickStats).first_or_none()


async def has_active_session(user_id: UUID) -> bool:
    """Check if the given user has an active session"""

    active_session = await SessionModel.find(
        SessionModel.assigned_user.fief_id == user_id,  # pylint: disable=no-member
        In(SessionModel.session_state,
           ACTIVE_SESSION_STATES),  # pylint: disable=no-member
        fetch_links=True
    ).sort((SessionModel.created_at, SortDirection.DESCENDING)).first_or_none()

    if active_session:
        raise UserHasActiveSessionException(user_id=user_id)

    return active_session is not None


async def get_active_session(user_id: ObjId) -> Optional[SessionView]:
    """Return the active session of a user, if any."""
    return await SessionModel.find(
        SessionModel.assigned_user.id == user_id,  # pylint: disable=no-member
        In(SessionModel.session_state,
           ACTIVE_SESSION_STATES),  # pylint: disable=no-member
        fetch_links=True
    ).sort(
        (SessionModel.created_at, SortDirection.DESCENDING)
    ).project(SessionView).first_or_none()


async def get_session_history(user_id: ObjId) -> List[SessionModel]:
    """Return the session history of a user."""
    return await SessionModel.find(
        SessionModel.assigned_user.id == user_id,  # pylint: disable=no-member
        fetch_links=True
    ).sort(
        (SessionModel.created_at, SortDirection.DESCENDING)
    ).project(SessionView).to_list()


async def get_expired_session_count(user_id: ObjId) -> int:
    return await SessionModel.find(
        SessionModel.assigned_user.id == user_id,  # pylint: disable=no-member
        SessionModel.session_state == SessionState.EXPIRED,
        SessionModel.created_at >= (datetime.now() - timedelta(hours=24)),
        fetch_links=True
    ).count()
