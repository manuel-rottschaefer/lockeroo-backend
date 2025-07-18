"""This module provides exception classes for station management."""
# beanie
# Log level
from logging import INFO

from beanie import PydanticObjectId as ObjId
# Exceptions
from fastapi import HTTPException


class ReviewNotFoundException(Exception):
    """Exception raised when a review cannot be found by a given query."""

    def __init__(self, review_id: ObjId = None):
        self.review = review_id
        self.log_level = INFO
        raise HTTPException(status_code=404, detail=self.__str__())

    def __str__(self):
        return f"Review '#{self.review}' not found in database.)"
