"""Provides utility functions for the the user management backend."""

# Types
from datetime import datetime, timedelta
from uuid import UUID
# Beanie
from beanie import PydanticObjectId as ObjId, SortDirection
from beanie.operators import In
# Models
from src.models.session_models import SessionModel, SessionState, ACTIVE_SESSION_STATES
# Exceptions
from src.exceptions.user_exceptions import UserHasActiveSessionException


async def has_active_session(user_id: UUID) -> bool:
    """Check if the given user has an active session"""

    active_session = await SessionModel.find(
        SessionModel.user.fief_id == user_id,  # pylint: disable=no-member
        In(SessionModel.session_state,
           ACTIVE_SESSION_STATES),  # pylint: disable=no-member
        fetch_links=True
    ).sort((SessionModel.created_at, SortDirection.DESCENDING)).first_or_none()

    if active_session:
        raise UserHasActiveSessionException(user_id=user_id)

    return active_session is not None


async def get_expired_session_count(user_id: ObjId) -> int:
    return await SessionModel.find(
        SessionModel.user.id == user_id,  # pylint: disable=no-member
        SessionModel.session_state == SessionState.EXPIRED,
        SessionModel.created_at >= (datetime.now() - timedelta(hours=24)),
        fetch_links=True
    ).count()
