"""Provides utility functions for the the account management backend."""

# Types
from uuid import UUID

# Beanie
from beanie.operators import NotIn

# Models
from src.models.session_models import SessionModel

# Services
from src.services.logging_services import logger


async def has_active_session(user_id: UUID) -> bool:
    """Check if the given user has an active session"""

    active_session = await SessionModel.find(
        SessionModel.assigned_user == user_id,
        SessionModel.session_state[1] is True  # pylint: disable=no-member
    ).first_or_none()

    if active_session:
        logger.info(f"User {user_id} already has an active session.")

    return active_session is not None
