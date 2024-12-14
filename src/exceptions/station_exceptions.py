"""This module provides exception classes for station management."""
# Beanie
from beanie import PydanticObjectId as ObjId

# Models
from src.models.station_models import TerminalStates

# Log level
from logging import INFO, WARNING


class StationNotFoundException(Exception):
    """Exception raised when a station cannot be found by a given query."""

    def __init__(self, callsign: str = None, station_id: ObjId = None):
        self.station = callsign if callsign else station_id
        self.log_level = INFO
        super().__init__(status_code=404, detail=self.__str__())

    def __str__(self):
        return f"Station '#{self.station}' not found in database.)"


class StationNotAvailableException(Exception):
    """Exception raised when a station is not available for the requested action."""

    def __init__(self, callsign: str):
        self.station = callsign
        self.log_level = INFO
        super().__init__(status_code=400, detail=self.__str__())

    def __str__(self):
        return f"Station '#{self.station}' is not available at the moment.)"


class InvalidStationReportException(Exception):
    """Exception raised when a station reports an action that is not expected by the backend."""

    def __init__(self, station_callsign: str, reported_state: str):
        self.station_callsign = station_callsign
        self.reported_state = reported_state
        self.log_level = WARNING

    def __str__(self):
        return f"Invalid station report of {
            self.reported_state} at station '{self.station_callsign}'.)"


class InvalidTerminalStateException(Exception):
    """Exception raised when a station reports a
    terminal mode that is not expected by the backend."""

    def __init__(self,
                 station_callsign: str,
                 expected_state: TerminalStates,
                 actual_state: TerminalStates):
        super().__init__()
        self.station_callsign = station_callsign
        self.expected_state = expected_state
        self.actual_state = actual_state

    def __str__(self):
        return f"Invalid station report at station '{self.station_callsign}'.)"
