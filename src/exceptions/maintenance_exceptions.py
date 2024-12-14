"""This module provides exception classes for maintenance management."""
# Beanie
from beanie import PydanticObjectId as ObjId

# Models
from src.models.maintenance_models import maintenanceStates

# Services
from src.services.logging_services import logger


class MaintenanceNotFoundException(Exception):
    """Exception raised no maintenance entry could be found with the given query."""

    def __init__(self, maintenance_id: ObjId):
        super().__init__()
        self.maintenance_id = maintenance_id
        logger.warning(
            f"Maintenance '{maintenance_id}' not found")

    def __str__(self):
        return f"Invalid state of maintenance '{self.session_id}'.)"
