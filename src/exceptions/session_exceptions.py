"""This module provides exception classes for session management."""
# Typing
from typing import List
# Beanie
from beanie import PydanticObjectId as ObjId
# Exceptions
from fastapi import HTTPException
# Log level
from logging import INFO, WARNING
# Models
from src.models.session_models import SessionStates


class SessionNotFoundException(Exception):
    """Exception raised when a station cannot be found by a given query."""

    def __init__(self, session_id: ObjId = None, raise_http: bool = True):
        self.session = session_id
        self.log_level = INFO

        if raise_http:
            raise HTTPException(status_code=404, detail=self.__str__())

    def __str__(self):
        return f"Session '#{self.session}' not found in database.)"


class InvalidSessionStateException(Exception):
    """Exception raised when a session is not matching the expected state."""

    def __init__(self, session_id: ObjId,
                 expected_states: List[SessionStates],
                 actual_state: SessionStates,
                 raise_http: bool = True):
        self.session_id = session_id
        self.expected_states = expected_states
        self.actual_state = actual_state
        self.log_level = WARNING

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return (f"Invalid state of session '#{self.session_id}':"
                f"Expected {self.expected_states}, got {self.actual_state}")
