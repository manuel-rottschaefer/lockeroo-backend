"""This module provides utilities for user management."""
# Beanie
from beanie.operators import In
# Entities
from src.entities.entity_utils import Entity
# Models
from src.models.user_models import UserModel
from src.models.session_models import SessionModel, SessionStates, ACTIVE_SESSION_STATES


class User(Entity):
    """Adds behaviour for a station instance."""
    document: UserModel

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
