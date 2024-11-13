"""Provides utility functions for the the account management backend."""

# Types
from uuid import UUID

# Beanie
from beanie.operators import NotIn

# Models
from src.models.session_models import SessionModel, INACTIVE_SESSION_STATES

# Services
from src.services.logging_services import logger


async def has_active_session(user_id: UUID) -> bool:
    """Check if the given user has an active session"""

    active_session = await SessionModel.find(
        SessionModel.assigned_user == user_id,
        NotIn(SessionModel.session_state, INACTIVE_SESSION_STATES)
    ).first_or_none()

    if active_session:
        logger.info(f"User {user_id} already has an active session.")

    return active_session is not None
