"""This module provides exception classes for locker management."""
# Beanie
from beanie import PydanticObjectId as ObjId
# Exceptions
from fastapi import HTTPException


class InvalidPaymentMethodException(Exception):
    """Exception raised when an invalid payment method is provided."""

    def __init__(self, session_id: ObjId, payment_method: str):
        self.session_id = session_id
        self.method = payment_method
        raise HTTPException(status_code=400, detail=self.__str__())

    def __str__(self):
        return (
            (f"Invalid payment method '{self.method.upper()}' "
             f"for session '#{self.session_id}'."))
