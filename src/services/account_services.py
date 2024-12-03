"""Provides utility functions for the the user management backend."""

# Types
from datetime import datetime, timedelta
from uuid import UUID

from beanie import PydanticObjectId as ObjId

# Models
from src.models.session_models import SessionModel, SessionStates
# Services
from src.services.logging_services import logger


async def has_active_session(user_id: ObjId) -> bool:
    """Check if the given user has an active session"""

    active_session = await SessionModel.find(
        SessionModel.belongs_to == user_id,
        SessionModel.session_state.is_active is True  # pylint: disable=no-member
    ).first_or_none()

    if active_session:
        logger.info(f"User {user_id} already has an active session.")

    return active_session is not None


async def get_expired_session_count(user_id: ObjId) -> int:
    return await SessionModel.find(
        SessionModel.user.id == user_id,  # pylint: disable=no-member
        SessionModel.session_state == SessionStates.EXPIRED,
        SessionModel.created_ts >= (datetime.now() - timedelta(hours=24)),
        fetch_links=True
    ).count()
