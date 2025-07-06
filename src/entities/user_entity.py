"""
Lockeroo.user_entity
-------------------------
This module provides the User Entity class

Key Features:
    - Provides a functionality wrapper for Beanie Documents

Dependencies:
    - beanie
"""
# Basics
from typing import Union
from datetime import datetime, timedelta, timezone
# Beanie
from beanie.operators import In, NotIn
# Entities
from src.entities.entity import Entity
# Models
from lockeroo_models.user_models import UserModel
from lockeroo_models.session_models import (
    ACTIVE_SESSION_STATES,
    SessionModel,
    SessionState)


class User(Entity):
    """
    Lockeroo.User
    -------
    A class representing a user. Users are private business clients
    that use lockers on a spontaneous basis

    Key Features:
    - `__init__`: Initializes a user object
    - 'has_active_session': Checks whether the user has an active session
    - 'active_session_count': Returns the amount of active sessions for that user
    - 'total_completed_session_count': Returns the amount of completed sessions for that user
    - 'expired_session_count': Returns the amount of expired sessions in a given timeframe
    """
    doc: Union[UserModel]

    def __init__(self, document=None):
        super().__init__(document)

    @property
    async def has_active_session(self) -> bool:
        """Checks whether the user has an active session

        Args:
            self User: The user Entity

        Returns:
            bool: Whether the user has an active session

        Raises:
            -

        Example:
            >>> user.has_active_session()
            True
        """
        session: SessionModel = await SessionModel.find(
            SessionModel.assigned_user.id == self.doc.id,  # pylint: disable=no-member
            In(SessionModel.session_state, ACTIVE_SESSION_STATES)
        ).first_or_none()
        return session is not None

    @property
    async def total_completed_session_count(self) -> int:
        """Returns the amount of completed sessions for this user

        Args:
            self User: The user Entity

        Returns:
            bool: The amount of completed sessions

        Raises:
            -

        Example:
            >>> user.total_completed_session_count()
            12
        """
        session_count: int = await SessionModel.find(
            SessionModel.assigned_user.id == self.doc.id,
            SessionModel.session_state == SessionState.COMPLETED
        ).count()
        return session_count

    @property
    async def active_session_count(self) -> int:
        """Returns the amount of active sessions for this user

        Args:
            self User: The user Entity

        Returns:
            bool: The amount of active sessions

        Raises:
            -

        Example:
            >>> user.active_session_count()
            True
        """
        session_count: int = await SessionModel.find(
            SessionModel.assigned_user.id == self.doc.id,
            In(UserModel.session_state, ACTIVE_SESSION_STATES)
        ).count()
        return session_count

    async def expired_session_count(self, timeframe: timedelta):
        """Returns the amount of expired sessions for this user

        Args:
            self User: The user Entity

        Returns:
            bool: The amount of expired sessions

        Raises:
            -

        Example:
            >>> user.expired_session_count()
            True
        """
        # Calculate the datetime for the start of the timeframe
        timeframe_start = datetime.now(timezone.utc) - timeframe
        # Query for sessions within the timeframe
        session_count = await SessionModel.find(
            SessionModel.assigned_user.id == self.doc.id,
            SessionModel.created_at < datetime.now(timezone.utc) - timeframe,
            SessionModel.created_at >= timeframe_start
        ).count()
        return session_count > 0
