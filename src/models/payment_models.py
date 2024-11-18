'''This module provides the Models for Payment events.'''
# Types
import dataclasses

# Basics
from datetime import datetime
from enum import Enum
from typing import Optional

# Types
from beanie import Document, Replace, after_event
from beanie import PydanticObjectId as ObjId
from beanie.operators import Set
from pydantic import Field

# Entities
from src.entities.session_entity import Session
from src.entities.station_entity import Station

# Services
from src.services.mqtt_services import fast_mqtt


class PaymentStates(Enum):
    """All possible states for a payment instance"""
    SCHEDULED = 'scheduled'
    PENDING = 'pending'
    COMPLETED = 'completed'
    EXPIRED = 'expired'
    ABORTED = 'aborted'


class PaymentModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a payment object in the database"""
    ### Identification ###
    id: Optional[ObjId] = Field(
        None, alias="_id", description='ObjectID in the database')

    assigned_session: ObjId = Field(
        description='Session to which the payment belongs to.')

    state: PaymentStates = Field(
        PaymentStates.SCHEDULED, description='Current state of the payment object.')

    price: int = Field(
        0, description='The calculated price of the assigned session at the time of creation.')

    last_updated: datetime = Field(datetime.now(),
                                   description='The timestamp of the last update to this payment.')

    @after_event(Replace)
    async def check_pending(self):
        """Check if this payment is now pending."""
        # 1: Update the timestamp
        await self.update(Set({PaymentModel.last_updated: datetime.now()}))

        if self.state == PaymentStates.PENDING:
            # Get the session
            session: Session = await Session().fetch(session_id=self.assigned_session)
            station: Station = await Station().fetch(station_id=session.assigned_station)
            fast_mqtt.publish(
                f'/stations/{station.call_sign}/payment/{self.price}')

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "payments"
