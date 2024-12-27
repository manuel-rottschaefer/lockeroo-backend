"""This module provides exception classes for maintenance management."""
# Beanie
# Log levels
from logging import INFO, WARNING

from beanie import PydanticObjectId as ObjId
# Exceptions
from fastapi import HTTPException

# Models
from src.models.maintenance_models import MaintenanceStates


class MaintenanceNotFoundException(Exception):
    """Exception raised no maintenance entry could be found with the given query."""

    def __init__(self, maintenance_id: ObjId, raise_http: bool = True):
        self.maintenance_id = maintenance_id
        self.log_level = INFO

        if raise_http:
            raise HTTPException(status_code=404, detail=self.__str__())

    def __str__(self):
        return f"Cannot find maintenance '#{self.maintenance_id}' in database.)"


class InvalidMaintenanceStateException(Exception):
    """Exception raised when an invalid maintenance state is provided."""

    def __init__(self, maintenance_id: ObjId,
                 expected_state: MaintenanceStates,
                 actual_state: MaintenanceStates):
        self.maintenance_id = maintenance_id
        self.expected_state = expected_state
        self.actual_state = actual_state
        self.log_level = WARNING
        raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return (
            f"Invalid provided for maintenance '#{self.maintenance_id}'. "
            f"Expected: {self.expected_state}, Actual: {self.actual_state}")
