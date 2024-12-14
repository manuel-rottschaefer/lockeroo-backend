"""This module provides exception classes for task management."""
# Typing
from typing import Union

# Beanie
from beanie import PydanticObjectId as ObjId

# Models
from src.models.task_models import TaskTypes
from src.models.session_models import SessionStates


class UserNotFoundException(Exception):
    """Exception raised when a user cannot be found by a given query."""

    def __init__(self, user_id: ObjId = None):
        self.user_id = user_id
        super().__init__(status_code=404, detail=self.__str__())

    def __str__(self):
        return (f"Could not find user '#{self.user_id}' in database.")


class UserNotAuthorizedException(Exception):
    """Exception raised when a user is not authorized to perform an action."""

    def __init__(self, user_id: ObjId = None):
        self.user_id = user_id
        super().__init__(status_code=401, detail=self.__str__())

    def __str__(self):
        return (f"User '#{self.user_id}' is not authorized to perform this action.")


class UserHasActiveSessionException(Exception):
    """Exception raised when a user already has an active session."""

    def __init__(self, user_id: ObjId = None):
        self.user_id = user_id
        super().__init__(status_code=400, detail=self.__str__())

    def __str__(self):
        return (f"User '#{self.user_id}' has an active session.")
