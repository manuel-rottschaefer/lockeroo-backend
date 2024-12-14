"""This module provides exception classes for station management."""
# Beanie
from beanie import PydanticObjectId as ObjId

# Models
from src.models.station_models import TerminalStates


class StationNotFoundException(Exception):
    """Exception raised when a station cannot be found by a given query."""

    def __init__(self, callsign: str = None, station_id: ObjId = None):
        super().__init__()
        self.station = callsign if callsign else station_id

    def __str__(self):
        return f"Station '{self.station}' not found.)"


class StationNotAvailableException(Exception):
    """Exception raised when a station is not available for the requested action."""

    def __init__(self, callsign: str):
        super().__init__()
        self.station = callsign

    def __str__(self):
        return f"Station '{self.station}' is not available.)"


class InvalidStationReportException(Exception):
    """Exception raised when a station reports an action that is not expected by the backend."""

    def __init__(self, station_callsign: str, reported_state: str):
        super().__init__()
        self.station_callsign = station_callsign
        self.reported_state = reported_state

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
