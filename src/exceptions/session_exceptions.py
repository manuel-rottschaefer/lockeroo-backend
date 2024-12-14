"""This module provides exception classes for session management."""
# Typing
from typing import List
# Beanie
from beanie import PydanticObjectId as ObjId
# Models
from src.models.session_models import SessionStates
# Log level
from logging import INFO, WARNING


class SessionNotFoundException(Exception):
    """Exception raised when a station cannot be found by a given query."""

    def __init__(self, session_id: ObjId = None):
        self.session = session_id
        self.log_level = INFO
        super().__init__(status_code=404, detail=self.__str__())

    def __str__(self):
        return f"Session '#{self.session}' not found in database.)"


class InvalidSessionStateException(Exception):
    """Exception raised when a session is not matching the expected state."""

    def __init__(self, session_id: ObjId,
                 expected_states: List[SessionStates],
                 actual_state: SessionStates):
        self.session_id = session_id
        self.expected_state = expected_states
        self.actual_state = actual_state
        self.log_level = WARNING
        super().__init__(status_code=400, detail=self.__str__())

    def __str__(self):
        return (f"Invalid state of session '#{self.session_id}':)"
                f"Expected: {self.expected_state}, Actual: {self.actual_state}")
