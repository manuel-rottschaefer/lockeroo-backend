"""
    Payment Utils Module
"""

# Basics
from typing import Optional
from datetime import datetime, timedelta

# Beanie
from beanie import PydanticObjectId as ObjId
from beanie import SortDirection, Replace
from beanie.operators import In, Set

# Configuration
from src.config.config import locker_config

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

        # 2: Check whether there exists an active payment
        active_payment: PaymentModel = await PaymentModel.find(
            PaymentModel.assigned_session == session_id,
            In(PaymentModel.state, [
               PaymentStates.SCHEDULED, PaymentStates.PENDING])
        ).sort((PaymentModel.last_updated, SortDirection.DESCENDING)).first_or_none()

        last_payment: PaymentModel = await PaymentModel.find(
            PaymentModel.assigned_session == session_id
        ).sort((PaymentModel.last_updated, SortDirection.DESCENDING)).first_or_none()

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
        return instance

    async def set_state(self, state: PaymentStates):
        await self.document.update(Set({PaymentModel.state: state}))

    async def get_price(self) -> Optional[int]:
        price = await self.current_price
        # TODO: This line is not working.
        # await self.document.update(Set({PaymentModel.price: price}))
        return price

    @property
    async def current_price(self) -> Optional[int]:
        """Calculate the total cost of a session in cents."""
        # 1: Get the assigned session
        session: Session = await Session().fetch(session_id=self.document.assigned_session)

        # 2: Get the locker assigned to this session
        locker: Locker = await Locker().fetch(locker_id=session.assigned_locker)

        # 3: Get the pricing model for this session
        locker_type = locker_config[locker.locker_type]

        # 4:Calculate the total cost
        active_duration: timedelta = await session.active_duration
        calculated_price: int = locker_type['minute_rate'] * \
            (active_duration.total_seconds() / 60)
        # 5: Assure that price is withing bounds
        calculated_price = min(
            max(calculated_price,
                locker_type['base_price']), locker_type['max_price']
        )

        logger.debug(
            f"Calculated price of {calculated_price} cents for session '{session.id}'.")

        return calculated_price
