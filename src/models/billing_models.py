"""
This module declares the models for bills.
The goal is to seperate the payment/billing process from the session internally,
making additional features easier to implement.
A bill is only issued after a completed session,
it is not meant for use within an active session
"""
# Basics
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# Database mapping
from beanie import Document
from beanie import PydanticObjectId as ObjId
# Types
from pydantic import Field


class BillPaymentMethod(str, Enum):
    """Enumeration of available payment methods"""
    TERMINAL = "terminal"
    PAYPAL = "paypal"
    STRIPE = "stripe"


class BillModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a bill in the database.
    A session may only have one connected bill"""

    ### Identification ###
    id: ObjId = Field(None, alias="_id")

    payment_method: BillPaymentMethod = Field(
        None, description="Selected payment method"
    )

    issued_at: datetime = Field(
        None, description="The timestamp at which the bill was requested."
    )

    @dataclass
    class Config:  # pylint: disable=missing-class-docstring
        json_schema_extra = {
            "payment_method": "paypal",
            "issued_at": "2023-10-10T10:00:00"
        }
