"""This module provides the Models for Payment events."""
# Types
import dataclasses

# Basics
from datetime import datetime
from typing import List, Optional
from enum import Enum
import yaml

# Types
from beanie import Document, Link, Update, after_event
from beanie import PydanticObjectId as ObjId
from beanie.operators import Set
from pydantic import BaseModel, Field

# Entities
from src.entities.session_entity import Session
from src.entities.station_entity import Station

# Models
from src.models.station_models import StationModel
from src.models.session_models import SessionModel

# Services
from src.services.mqtt_services import fast_mqtt


class PaymentStates(Enum):
    """All possible states for a payment instance"""
    SCHEDULED = 'scheduled'
    PENDING = 'pending'
    COMPLETED = 'completed'
    EXPIRED = 'expired'
    ABORTED = 'aborted'


class PricingModel(BaseModel):
    """Config representation of pricing models."""
    name: str = Field(description="Name of the pricing model"),
    base_fee: int = Field(
        description="Minimal charge when starting a session (cent)."),
    charge_fee: int = Field(
        description="Additional fee for connecting a device to the outlet.")
    base_duration: int = Field(
        description="Minutes until the charge exceeds the base charge."),
    rate_minute: float = Field(
        description="Charge for every started minue (cent)")


class PaymentModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a payment object in the database"""
    ### Identification ###
    id: Optional[ObjId] = Field(
        None, alias="_id", description='ObjectID in the database')

    assigned_station: Link[StationModel] = Field(
        description="Station at which the payment process is conducted.")

    assigned_session: Link[SessionModel] = Field(
        description='Session to which the payment belongs to.')

    state: PaymentStates = Field(
        PaymentStates.SCHEDULED, description='Current state of the payment object.')

    price: int = Field(
        0, description='The calculated price of the assigned session at the time of creation.')

    last_updated: datetime = Field(datetime.now(),
                                   description='The timestamp of the last update to this payment.')

    @after_event(Update)
    async def check_pending(self):
        """Check if this payment is now pending."""
        # 1: Update the timestamp
        await self.update(Set({PaymentModel.last_updated: datetime.now()}))

        if self.state == PaymentStates.PENDING:
            # Get the session
            session: Session = Session(self.assigned_session)
            await session.document.fetch_all_links()
            station: Station = await Station(session.assigned_station)
            fast_mqtt.publish(
                f'/stations/{station.call_sign}/payment/{self.price}')

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "payments"
