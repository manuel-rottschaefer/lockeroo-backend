"""This module provides utilities for  database for payments."""

# Basics
from datetime import datetime, timedelta
from typing import Optional

# Beanie
from beanie import SortDirection
from beanie.operators import In, Set

# Entities
from src.entities.entity_utils import Entity
from src.entities.locker_entity import Locker
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.models.payment_models import PaymentModel, PaymentStates, PricingModel
from src.models.session_models import SessionModel
# Models
from src.models.station_models import TerminalStates
# Services
from src.services.payment_services import PRICING_MODELS


class Payment(Entity):
    """Add behaviour to a payment Entity."""
    document: PaymentModel

    @classmethod
    async def fetch(cls,
                    session: SessionModel):
        """Get the current active or latest payment item of a session."""
        # 1: Create the instance
        instance = cls()

        # 2: Check whether there exists an active payment
        active_payment: PaymentModel = await PaymentModel.find(
            PaymentModel.assigned_session.id == session.id,  # pylint: disable=no-member
            In(PaymentModel.state, [
               PaymentStates.SCHEDULED, PaymentStates.PENDING]),
            fetch_links=True
        ).sort((PaymentModel.last_updated, SortDirection.DESCENDING)).first_or_none()

        last_payment: PaymentModel = await PaymentModel.find_one(
            PaymentModel.assigned_session.id == session.id,  # pylint: disable=no-member
            fetch_links=True
        ).sort((PaymentModel.last_updated, SortDirection.DESCENDING)).first_or_none()

        if active_payment:
            instance.document = active_payment
        elif last_payment:
            instance.document = last_payment
        else:
            instance.document = None
        return instance

    @classmethod
    async def create(cls, session: SessionModel):
        """Create a new payment item and insert it into the database."""
        instance = cls()

        instance.document = PaymentModel(
            assigned_station=session.assigned_station,
            assigned_session=session,
            state=PaymentStates.SCHEDULED,
            last_updated=datetime.now()
        )
        await instance.document.insert()
        return instance

    async def set_state(self, state: PaymentStates):
        """Set the state of the current session."""
        await self.document.update(Set({PaymentModel.state: state}))

    @property
    async def current_price(self) -> Optional[int]:
        """Calculate the total cost of a session in cents."""
        # 1: Get the assigned session
        await self.document.fetch_all_links()
        session: Session = Session(self.document.assigned_session)

        # 2: Get the locker assigned to this session
        locker: Locker = Locker(session.assigned_locker)

        pricing_model: PricingModel = PRICING_MODELS[locker.pricing_model]

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
        await self.document.fetch_all_links()
        self.document.price = await self.current_price

        station: Station = Station(self.document.assigned_station)
        await station.register_terminal_state(TerminalStates.PAYMENT)
