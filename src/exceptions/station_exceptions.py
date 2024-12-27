"""This module provides exception classes for station management."""
# Types
# Log level
from logging import INFO, WARNING
from typing import List

# Beanie
from beanie import PydanticObjectId as ObjId
# Exceptions
from fastapi import HTTPException

# Models
from src.models.station_models import TerminalState


class StationNotFoundException(Exception):
    """Exception raised when a station cannot be found by a given query."""

    def __init__(self,
                 callsign: str = None,
                 station_id: ObjId = None,
                 raise_http: bool = True):
        self.station = callsign if callsign else station_id
        self.log_level = INFO

        if raise_http:
            raise HTTPException(status_code=404, detail=self.__str__())

    def __str__(self):
        return f"Station '#{self.station}' not found in database.)"


class StationNotAvailableException(Exception):
    """Exception raised when a station is not available for the requested action."""

    def __init__(self, callsign: str):
        self.station = callsign
        self.log_level = INFO
        raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return f"Station '#{self.station}' is not available at the moment.)"


class InvalidStationReportException(Exception):
    """Exception raised when a station reports an action that is not expected by the backend."""

    def __init__(self,
                 station_callsign: str,
                 reported_state: str,
                 raise_http: bool = True):
        self.station_callsign = station_callsign
        self.reported_state = reported_state
        self.log_level = WARNING

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return f"Invalid station report of {
            self.reported_state} at station '#{self.station_callsign}'.)"


class InvalidTerminalStateException(Exception):
    """Exception raised when a station reports a
    terminal mode that is not expected by the backend."""

    def __init__(self,
                 station_callsign: str,
                 expected_states: List[TerminalState],
                 actual_state: TerminalState,
                 raise_http: bool = True):
        self.station_callsign = station_callsign
        self.expected_states = expected_states
        self.actual_state = actual_state

        if raise_http:
            raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return (f"Invalid terminal state at station '#{self.station_callsign}'."
                f" Expected '{[state for state in self.expected_states]}', got '{self.actual_state}'.")
