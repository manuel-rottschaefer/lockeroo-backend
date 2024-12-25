"""This module provides utilities for user management."""
# Basics
from datetime import datetime, timedelta
# Beanie
from beanie.operators import In, NotIn
# Entities
from src.entities.entity_utils import Entity
# Models
from src.models.user_models import UserModel
from src.models.session_models import SessionModel, SessionState, ACTIVE_SESSION_STATES


class User(Entity):
    """Adds behaviour for a station instance."""
    doc: UserModel

    ### Attributes ###
    @property
    def exists(self) -> bool:
        """Check whether the station entity has a document."""
        return self.doc is not None

    @property
    async def has_active_session(self) -> bool:
        """Check whether the user has an active session."""
        session: SessionModel = await SessionModel.find_one(
            SessionModel.user == self.doc.id,
            In(SessionModel.session_state, ACTIVE_SESSION_STATES)
        )
        return session is not None

    @property
    async def total_completed_session_count(self) -> int:
        """Get the total amount of sessions conducted at this station, without active ones."""
        session_count: int = await SessionModel.find(
            SessionModel.user == self.doc.id,
            SessionModel.session_state == SessionState.COMPLETED
        ).count()
        return session_count

    @property
    async def active_session_count(self) -> int:
        """Get the total amount of currently active stations at this station."""
        session_count: int = await UserModel.find(
            UserModel.assigned_station == self.doc.id,
            In(UserModel.session_state, ACTIVE_SESSION_STATES)
        ).count()
        return session_count

    async def get_expired_session_count(self, timeframe: timedelta):
        """Get the amount of sessions that have expired in the given timeframe."""
        session_count: int = await SessionModel.find(
            SessionModel.user == self.doc.id,
            NotIn(SessionModel.session_state, ACTIVE_SESSION_STATES),
            SessionModel.created_at < datetime.now() - timeframe,
        ).count()
        return session_count
