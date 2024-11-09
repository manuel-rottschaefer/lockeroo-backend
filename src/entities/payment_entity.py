"""
    Payment Utils Module
"""

# Basics
from typing import Optional
from datetime import datetime
# Beanie
from beanie import PydanticObjectId as ObjId
from beanie import SortDirection
# Entities
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker
# Models
from src.models.payment_models import PaymentModel, PaymentStates
# Services
from src.services.logging_services import logger


class Payment():
    """Add behaviour to a payment Entity."""

    def __getattr__(self, name):
        """Delegate attribute access to the internal document."""
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the internal document, except for 'document' itself."""
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    def __init__(self, document: PaymentModel = None):
        super().__init__()
        self.document = document

    @classmethod
    async def fetch(cls, session_id: ObjId):
        """Get the current active or latest payment item of a session."""
        # 1: Create the instance
        instance = cls()

        # 2: Check wether there exists an active payment
        active_payment: PaymentModel = await PaymentModel.find(
            PaymentModel.assigned_session == session_id,
            PaymentModel.state == PaymentStates.PENDING
        ).first_or_none()

        last_payment: PaymentModel = await PaymentModel.find(
            PaymentModel.assigned_session == session_id,
            PaymentModel.state == PaymentStates.COMPLETED
        ).sort(PaymentModel.last_updated, SortDirection.DESCENDING).first_or_none()

        if active_payment:
            instance.document = active_payment
        elif last_payment:
            instance.document = last_payment
        else:
            instance.document = None
        return instance

    @classmethod
    async def create(cls, session_id: ObjId):
        """Create a new queue item and insert it into the database."""
        instance = cls()

        instance.document = PaymentModel(
            assigned_session=session_id,
            state=PaymentStates.SCHEDULED,
            last_updated=datetime.now()
        )
        await instance.document.insert()
        logger.debug(f"Add payment entry for session '{session_id}'.")

        return instance

    async def activate(self):
        """Activate this payment."""
        logger.debug('ACTIVATED payment')
        self.document.state = PaymentStates.PENDING
        await self.document.replace()

    @property
    async def current_price(self) -> Optional[int]:
        """Calculate the total cost of a session in cents."""
        # 1: Get the assigned session
        session: Session = await Session().fetch(self.document.assigned_session)

        # 2: Get the locker assigned to this session
        locker: Locker = await Locker().fetch(session.assigned_locker)

        # 3: Get the pricing model for this session
        pricing_model = locker.type.pricing

        # 4:Calculate the total cost
        calculated_price: int = await pricing_model.minute_rate * (
            self.document.active_duration / 60
        )

        # 5: Assure that price is withing bounds
        calculated_price = min(
            max(calculated_price, pricing_model.min_price), pricing_model.max_price
        )

        logger.info(
            "Calculated price of %d cents for session '%s'.", calculated_price, self.id
        )

        return calculated_price
