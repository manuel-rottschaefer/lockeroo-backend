"""Provides utility functions for the action backend."""

# Basics
from datetime import datetime
# Beanie
from beanie import PydanticObjectId as ObjId
# Models
from src.models.action_models import ActionModel
from src.models.session_models import SessionStates


async def create_action(session_id: ObjId,
                        action_type: SessionStates) -> ActionModel:
    """Create a new action entry"""
    new_action = await ActionModel(
        assigned_session=session_id,
        action_type=action_type.name,
        timestamp=datetime.now()
    ).insert()

    if new_action:
        return new_action
