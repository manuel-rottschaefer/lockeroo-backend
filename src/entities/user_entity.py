"""This module provides utilities for user management."""

# Basics
from typing import Optional

# Beanie
from beanie import PydanticObjectId as ObjId
from beanie import SortDirection
from beanie.operators import In

# Entities
from src.entities.entity_utils import Entity
# Models
from src.models.user_models import UserModel
from src.models.session_models import SessionModel, SessionStates, ACTIVE_SESSION_STATES
# Logging
from src.services.logging_services import logger


class User(Entity):
    """Adds behaviour for a station instance."""
    @classmethod
    async def find(
        cls,
        user_id: Optional[ObjId] = None,
    ):
        """Find a session in the database"""
        instance = cls()

        query = {
            UserModel.id: user_id,
        }

        # Filter out None values
        query = {k: v for k, v in query.items() if v is not None}

        user_item: UserModel = await UserModel.find_one(
            query).sort((UserModel.created_ts,
        SortDirection.DESCENDING))

        instance.document = user_item
        return instance

    ### Attributes ###
    @property
    def exists(self) -> bool:
        """Check whether the station entity has a document."""
        return self.document is not None

    @property
    async def total_completed_session_count(self) -> int:
        """Get the total amount of sessions conducted at this station, without active ones."""
        session_count: int = await SessionModel.find(
            SessionModel.user == self.document.id,
            SessionModel.session_state == SessionStates.COMPLETED
        ).count()
        return session_count

    @property
    async def active_session_count(self) -> int:
        """Get the total amount of currently active stations at this station."""
        session_count: int = await UserModel.find(
            UserModel.assigned_station == self.document.id,
            In(UserModel.session_state, ACTIVE_SESSION_STATES)
        ).count()
        return session_count