"""This module provides utilities for  database for payments."""
# Basics
from datetime import datetime, timedelta
from typing import Optional
# Entities
from src.entities.entity_utils import Entity
from src.entities.locker_entity import Locker
from src.entities.session_entity import Session
from src.models.payment_models import PaymentModel, PaymentState, PricingModel
from src.models.session_models import SessionModel
# Services
from src.services.payment_services import PRICING_MODELS


class Payment(Entity):
    """Add behaviour to a payment Entity."""
    doc: PaymentModel

    @classmethod
    async def create(cls, session: SessionModel):
        """Create a new payment item and insert it into the database."""
        instance = cls()

        instance.doc = PaymentModel(
            assigned_station=session.assigned_station,
            assigned_session=session,
            state=PaymentState.SCHEDULED,
            last_updated=datetime.now()
        )
        await instance.doc.insert()
        return instance

    @property
    async def current_price(self) -> Optional[int]:
        """Calculate the total cost of a session in cents."""
        # 1: Get the assigned session
        await self.doc.fetch_link(PaymentModel.assigned_session)
        assert (PaymentModel.assigned_session
                ), f"Payment '#{self.doc.id}' has no assigned session."
        session: Session = Session(self.doc.assigned_session)

        # 2: Get the locker assigned to this session
        locker: Locker = Locker(session.assigned_locker)

        pricing_model: PricingModel = PRICING_MODELS[
            locker.locker_type.pricing_model]

        # 4:Calculate the total cost
        active_duration: timedelta = await session.active_duration
        calculated_price: int = pricing_model.rate_minute * \
            (active_duration.total_seconds() / 60)
        # 5: Assure that price is withing bounds
        # calculated_price = min(
        #    max(calculated_price,
        #        pricing_model['base_fee']), pricing_model['max_price']
        # )

        return calculated_price

    async def activate(self):
        """Activate the session by calculating the price, then sending it to the terminal."""
        await self.doc.fetch_all_links()
        self.doc.price = await self.current_price
