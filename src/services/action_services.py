"""
This file contains the services for the actions.
"""

# Basics
from datetime import datetime

from beanie import PydanticObjectId as ObjId

# Models
from src.models.action_models import ActionModel
from src.models.session_models import SessionStates

# Services
from src.services.logging_services import logger


async def create_action(session_id: ObjId,
                        action_type: SessionStates) -> ActionModel:
    """Create a new action entry"""
    new_action = await ActionModel(
        assigned_session=session_id,
        action_type=action_type,
        timestamp=datetime.now()
    ).insert()

    if new_action:
        return new_action

    logger.info('Tried to add action of type %s for session %s, but failed.',
                action_type.value, session_id)
