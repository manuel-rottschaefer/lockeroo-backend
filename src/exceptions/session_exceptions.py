"""This module provides exception classes for session management."""
# Beanie
from beanie import PydanticObjectId as ObjId
# Models
from src.models.session_models import SessionStates
# Services
from src.services.logging_services import logger


class InvalidSessionStateException(Exception):
    """Exception raised when a session is not matching the expected state."""

    def __init__(self, session_id: ObjId,
                 expected_state: SessionStates,
                 actual_state: SessionStates):
        super().__init__()
        self.session_id = session_id
        self.expected_state = expected_state
        self.actual_state = actual_state
        logger.warning(
            f"Session '{session_id}' should be in {
                expected_state}, but is currently registered as {actual_state}.")

    def __str__(self):
        return f"Invalid state of session '{self.session_id}'.)"


class SessionNotFoundException(Exception):
    """Exception raised when a station cannot be found by a given query."""

    def __init__(self, session_id: ObjId = None):
        super().__init__()
        self.session = session_id
        logger.warning(
            f"Could not find session '{self.session}' in database.")

    def __str__(self):
        return f"Session '{self.session}' not found.)"
