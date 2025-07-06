"""This module provides exception classes for session management."""
# Types
from logging import INFO, WARNING
from typing import List
from uuid import UUID
# beanie
from beanie import PydanticObjectId as ObjId
# Exceptions
from fastapi import HTTPException
# Models
from lockeroo_models.session_models import SessionState


class SessionNotFoundException(Exception):
    """Exception raised when a station cannot be found by a given query."""

    def __init__(self, user_id: UUID = None, raise_http: bool = True):
        self.user_id = user_id
        self.log_level = INFO

        if raise_http:
            raise HTTPException(status_code=404, detail=self.__str__())

    def __str__(self):
        return f"Cannot find session for user '#{self.user_id}' in the database.)"


class InvalidSessionStateException(Exception):
    """Exception raised when a session is not matching the expected state."""

    def __init__(self, session_id: ObjId,
                 expected_states: List[SessionState],
                 actual_state: SessionState,
                 raise_http: bool = True):
        self.session_id = session_id
        self.expected_states = expected_states
        self.actual_state = actual_state
        self.log_level = WARNING

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return (f"Invalid state of session '#{self.session_id}':"
                f"Expected {[state for state in self.expected_states]}, "
                f"got {self.actual_state}")
