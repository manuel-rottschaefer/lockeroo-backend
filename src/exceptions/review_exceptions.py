"""This module provides exception classes for station management."""
# Beanie
from beanie import PydanticObjectId as ObjId

# Log level
from logging import INFO, WARNING


class ReviewNotFoundException(Exception):
    """Exception raised when a review cannot be found by a given query."""

    def __init__(self, review_id: ObjId = None):
        self.review = review_id
        self.log_level = INFO
        super().__init__(status_code=404, detail=self.__str__())

    def __str__(self):
        return f"Review '#{self.review}' not found in database.)"
