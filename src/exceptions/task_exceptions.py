"""This module provides exception classes for task management."""
# Typing
from typing import Union

# Beanie
from beanie import PydanticObjectId as ObjId

# Models
from src.models.task_models import TaskTypes
from src.models.session_models import SessionStates

# Services
from src.services.logging_services import logger


class TaskNotFoundException(Exception):
    """Exception raised when a task cannot be found by a given query."""

    def __init__(self, task_id: ObjId = None,
                 queued_state: SessionStates = None,
                 assigned_station: Union[ObjId, str] = None,
                 task_type: TaskTypes = None):
        super().__init__()
        self.task_id = task_id
        self.queued_state = queued_state
        self.station = assigned_station
        self.type = task_type
        logger.warning(
            f"Could not find task of type '{self.type}', awaiting {self.queued_state} at station {self.station}.")

    def __str__(self):
        return f"Task '{self.task_id}' not found.)"
