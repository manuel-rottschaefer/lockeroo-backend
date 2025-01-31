"""This module provides exception classes for task management."""
# Types
from typing import Union

# Beanie
from beanie import PydanticObjectId as ObjId
# Exceptions
from fastapi import HTTPException

# Models
from src.models.task_models import TaskType


class TaskNotFoundException(Exception):
    """Exception raised when a task cannot be found by a given query."""

    def __init__(self,
                 assigned_station: Union[ObjId, str] = None,
                 task_type: TaskType = None,
                 raise_http: bool = True):
        self.station = assigned_station
        self.type = task_type

        if raise_http:
            raise HTTPException(status_code=404, detail=self.__str__())

    def __str__(self):
        return (f"Could not find task of type {self.type}"
                f" at station '{self.station}'.")
