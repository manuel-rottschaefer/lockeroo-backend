# Types
import dataclasses

# Basics
from datetime import datetime
from enum import Enum
from typing import Optional

# Types
from beanie import Document, Replace, after_event
from beanie import PydanticObjectId as ObjId
from pydantic import Field

# Entities
from ..entities.session_entity import Session

# Models
from ..models.session_models import SessionModel

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
        self.last_updated = datetime.now()
        await self.replace()

        if self.state == PaymentStates.PENDING:
            # Get the session
            session: Session = Session(await SessionModel.get(self.assigned_session))
            fast_mqtt.publish(
                f'/stations/{session.assigned_station}/payment/{self.price}')

    @dataclasses.dataclass
    class Settings:
        """Name in database"""
        name = "payments"
