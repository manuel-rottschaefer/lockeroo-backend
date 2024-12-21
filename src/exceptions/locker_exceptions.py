"""This module provides exception classes for locker management."""
# Types
from typing import Optional
# Beanie
from beanie import PydanticObjectId as ObjId
# Models
from src.models.locker_models import LockerStates, LockerTypes
# Exceptions
from fastapi import HTTPException


class LockerNotFoundException(Exception):
    """Exception raised when a locker is not found in the database."""

    def __init__(self,
                 locker_id: ObjId = None,
                 station: ObjId = None,
                 locker_index: int = None,
                 raise_http: bool = True):
        self.locker_id = locker_id
        self.station = station
        self.locker_index = locker_index

        if raise_http:
            raise HTTPException(status_code=500, detail=self.__str__())

    def __str__(self):
        if self.locker_id:
            return f"Locker '#{self.locker_id}' not found in database."
        elif self.station and self.locker_index:
            return (
                (f"Locker at station '#{self.station}' with index '"
                 f"{self.locker_index}' not found in database."))


class LockerNotAvailableException(Exception):
    """Exception raised when a locker is not available for the requested action."""

    def __init__(self, station_callsign: ObjId, raise_http: bool = True):
        self.assigned_station = station_callsign

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return f"Locker at station '#{self.assigned_station}' is not available."


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


class InvalidLockerReportException(Exception):
    """Exception raised when a locker report is not valid."""

    def __init__(self,
                 locker_id:  Optional[ObjId] = None,
                 locker_index: Optional[int] = None,
                 raise_http: bool = True):
        self.locker_id = locker_id
        self.locker_index = locker_index

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        if self.locker_id:
            return f"Invalid locker report for locker '#{self.locker_id}'."
        elif self.locker_index:
            return f"Invalid locker report for locker index '{self.locker_index}'."
