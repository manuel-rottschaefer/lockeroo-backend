"""This module provides exception classes for locker management."""
# Beanie
from beanie import PydanticObjectId as ObjId
# Models
from src.models.locker_models import LockerStates, LockerTypes
# Exceptions
from fastapi import HTTPException


class LockerNotFoundException(Exception):
    """Exception raised when a locker is not found in the database."""

    def __init__(self, locker_id: ObjId, raise_http: bool = True):
        self.locker_id = locker_id

        if raise_http:
            raise HTTPException(status_code=500, detail=self.__str__())

    def __str__(self):
        return f"Locker '#{self.locker_id}' not found in database."


class LockerNotAvailableException(Exception):
    """Exception raised when a locker is not available for the requested action."""

    def __init__(self, locker_id: ObjId, raise_http: bool = True):
        self.locker_id = locker_id

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return f"Locker '#{self.locker_id}' is not available."


class InvalidLockerTypeException(Exception):
    """Exception raised when a locker type is not found in the configuration."""

    def __init__(self,
                 locker_type: LockerTypes,
                 raise_http: bool = True):
        self.locker_type = locker_type

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return f"Locker type '{self.locker_type}' is not found in the configuration."


class InvalidLockerStateException(Exception):
    """Exception raised when a session session is in a state that is not expected by the backend."""

    def __init__(self, locker_id: ObjId,
                 expected_state: LockerStates,
                 actual_state: LockerStates,
                 raise_http: bool = True):
        self.locker_id = locker_id
        self.expected_state = expected_state
        self.actual_state = actual_state

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return (f"Invalid state of locker '#{self.locker_id}'.)"
                f"Expected: {self.expected_state}, Actual: {self.actual_state}")
