"""This module provides exception classes for locker management."""
# Types
from typing import Optional
# Beanie
from beanie import PydanticObjectId as ObjId
# Exceptions
from fastapi import HTTPException
# Models
from src.models.locker_models import LockerState, LockerType
# Logging
from src.services.logging_services import logger


class LockerNotFoundException(Exception):
    """Exception raised when a locker is not found in the database."""

    def __init__(self,
                 locker_id: ObjId = None,
                 station_callsign: ObjId = None,
                 station_index: int = None,
                 raise_http: bool = True):
        self.locker_id = locker_id
        self.station_callsign = str(station_callsign)
        self.station_index = station_index

        if raise_http:
            raise HTTPException(status_code=404, detail=self.__str__())

    def __str__(self):
        if self.locker_id:
            return f"Locker '#{self.locker_id}' not found in database."
        elif self.station_callsign and self.station_index:
            return (
                (f"Locker at station '{self.station_callsign}' with index '"
                 f"{self.station_index}' not found in database."))


class LockerNotAvailableException(Exception):
    """Exception raised when a locker is not available for the requested action."""

    def __init__(self,
                 station_callsign: ObjId,
                 locker_type: LockerType,
                 raise_http: bool = True):
        self.assigned_station = station_callsign
        self.locker_type = locker_type
        self.log_level = logger.warning

        if raise_http:
            raise HTTPException(status_code=404, detail=self.__str__())

    def __str__(self):
        return (
            f"No Locker of type '{self.locker_type.name}' available "
            f"at station '#{self.assigned_station}'.")


class InvalidLockerTypeException(Exception):
    """Exception raised when a locker type is not found in the configuration."""

    def __init__(self,
                 locker_type: LockerType,
                 raise_http: bool = True):
        self.locker_type = locker_type

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return f"Locker type '{self.locker_type}' is not found in the configuration."


class InvalidLockerStateException(Exception):
    """Exception raised when a session session is in a state that is not expected by the backend."""

    def __init__(self, locker_id: ObjId,
                 expected_state: LockerState,
                 actual_state: LockerState,
                 raise_http: bool = True):
        self.locker_id = locker_id
        self.expected_state = expected_state
        self.actual_state = actual_state

        logger.error(self.__str__())

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return (f"Invalid state of locker '#{self.locker_id}'. "
                f"Expected: {self.expected_state}, Actual: {self.actual_state}")


class InvalidLockerReportException(Exception):
    """Exception raised when a locker report is not valid."""

    def __init__(self,
                 locker_id:  Optional[ObjId] = None,
                 station_index: Optional[int] = None,
                 raise_http: bool = True):
        self.locker_id = locker_id
        self.station_index = station_index

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        if self.locker_id:
            return f"Invalid locker report for locker '#{self.locker_id}'."
        elif self.station_index:
            return f"Invalid locker report for locker index '{self.station_index}'."
