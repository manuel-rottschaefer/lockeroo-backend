"""Provides utility functions for the the account management backend."""

# Types
from uuid import UUID

# Models
from src.models.session_models import SessionModel

# Services
from src.services.logging_services import logger


async def has_active_session(account_id: UUID) -> bool:
    """Check if the given account has an active session"""

    active_session = await SessionModel.find(
        SessionModel.belongs_to == account_id,
        SessionModel.session_state.is_active is True  # pylint: disable=no-member
    ).first_or_none()

    if active_session:
        logger.info(f"Account '{account_id}' already has an active session.")

    return active_session is not None
