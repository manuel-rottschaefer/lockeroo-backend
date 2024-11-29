"""
This module declares the models for bills.
The goal is to seperate the payment/billing process from the session internally,
making additional features easier to implement.
A bill is only issued after a completed session,
it is not meant for use within an active session
"""
# Basics
from datetime import datetime
from enum import Enum

# Types
from pydantic import Field

# Database mapping
from beanie import Document
from beanie import PydanticObjectId as ObjId


class BillPaymentMethods(Enum, str):
    """Enumeration of available payment methods"""

    TERMINAL = "terminal"
    PAYPAL = "paypal"
    STRIPE = "stripe"


class BillModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a bill in the database.
    A session may only have one connected bill"""

    ### Identification ###
    id: ObjId = Field(alias="_id")

    payment_method: BillPaymentMethods = Field(
        None, description="Selected payment method"
    )

    issued_ts: datetime = Field(
        None, description="The timestamp at which the bill was requested."
    )
