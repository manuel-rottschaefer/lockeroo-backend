"""This module provides exception classes for locker management."""
# Beanie
from beanie import PydanticObjectId as ObjId

# Models
from src.models.locker_models import LockerStates

# Services
from src.services.logging_services import logger


class InvalidPaymentMethodException(Exception):
    """Exception raised when an invalid payment method is provided."""

    def __init__(self, session_id: ObjId):
        self.session_id = session_id
        super().__init__(status_code=400, detail=self.__str__())

    def __str__(self):
        return (f"Invalid payment method for session '#{self.session_id}'.")
