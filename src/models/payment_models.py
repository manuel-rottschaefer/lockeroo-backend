"""This module provides the Models for Payment events."""
# Types
from dataclasses import dataclass
# Basics
from datetime import datetime
from enum import Enum

# Types
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import SaveChanges, after_event
from pydantic import BaseModel, Field, PydanticUserError

# Entities
from src.models.session_models import SessionModel
# Models
from src.models.station_models import StationModel
# Services
from src.services.mqtt_services import fast_mqtt


class PaymentState(Enum):
    """All possible states for a payment instance"""
    SCHEDULED = 'scheduled'
    PENDING = 'pending'
    COMPLETED = 'completed'
    EXPIRED = 'expired'
    ABORTED = 'aborted'


class PaymentModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a payment object in the database"""
    ### Identification ###
    id: ObjId = Field(None, alias="_id")

    assigned_station: Link[StationModel] = Field(
        description="Station at which the payment process is conducted.")

    assigned_session: Link[SessionModel] = Field(
        description='Session to which the payment belongs to.')

    state: PaymentState = Field(
        PaymentState.SCHEDULED,
        description='Current state of the payment object.')

    price: int = Field(
        default=0,
        description='The calculated price of the assigned session at the time of creation.')

    last_updated: datetime = Field(
        datetime.now(), description='The timestamp of the last update to this payment.')

    @after_event(SaveChanges)
    async def check_pending(self):
        """Check if this payment is now pending."""
        self.assigned_station: StationModel
        # 1: Update the timestamp
        self.doc.last_updated = datetime.now()

        # 2: Check if the payment is now pending
        if self.state == PaymentState.PENDING:
            await self.fetch_link(SessionModel.assigned_station)
            fast_mqtt.publish(
                f'/stations/{self.assigned_station.callsign}/payment/{self.price}')

        await self.doc.save_changes()

    @dataclass
    class Settings:
        name = "payments"

    @dataclass
    class Config:
        json_schema_extra = {
            "assigned_station": "60d5ec49f1d2b2a5d8f8b8b8",
            "assigned_session": "60d5ec49f1d2b2a5d8f8b8b8",
            "state": "scheduled",
            "price": 1000,
            "last_updated": "2023-10-10T10:00:00"
        }


try:
    for model in [PaymentModel]:
        model.model_json_schema()
except PydanticUserError as exc_info:
    assert exc_info.code == 'invalid-for-json-schema'
