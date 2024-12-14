"""This module provides exception classes for locker management."""
# Beanie
from beanie import PydanticObjectId as ObjId

# Models
from src.models.locker_models import LockerStates

# Services
from src.services.logging_services import logger


class LockerNotFoundException(Exception):
    """Exception raised when a locker is not found in the database."""

    def __init__(self, locker_id: ObjId):
        super().__init__()
        self.locker_id = locker_id
        logger.warning(f"Locker '{locker_id}' could not be found.")

    def __str__(self):
        return f"Locker '{self.locker_id}' not found."


class InvalidLockerStateException(Exception):
    """Exception raised when a session session is in a state that is not expected by the backend."""

    def __init__(self, locker_id: ObjId,
                 expected_state: LockerStates,
                 actual_state: LockerStates):
        super().__init__()
        self.locker_id = locker_id
        self.expected_state = expected_state
        self.actual_state = actual_state
        logger.warning(
            f"Locker '{locker_id}' should be in {
                expected_state}, but is currently registered as {actual_state}.")

    def __str__(self):
        return f"Invalid state of locker '{self.locker_id}'.)"
