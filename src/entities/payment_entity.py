"""
Lockeroo.payment_entity
-------------------------
This module provides the Payment Entity class

Key Features:
    - Provides a functionality wrapper for Beanie Documents

Dependencies:
    - beanie
"""
# Basics
from datetime import datetime, timedelta, timezone
from typing import Optional
# Entities
from src.entities.entity import Entity
from src.entities.locker_entity import Locker, LockerType
from src.entities.session_entity import Session
# Models
from lockeroo_models.locker_models import PricingModel
from lockeroo_models.payment_models import PaymentModel, PaymentState
from lockeroo_models.session_models import SessionModel
# Services
from src.services.mqtt_services import fast_mqtt
from src.services.locker_services import LOCKER_TYPES


class Payment(Entity):
    """
    Lockeroo.Payment
    -------
    A class representing a payment. A Payment is the process of selecting, verifying and applying
    a payment method, utilizing the mobile app or the station terminal.

    Key Features:
    - `__init__`: Initializes a payment object and adds event logic to it
    - 'create': Creates a payment object and inserts it into the database
    - 'current_price': Gets the current price of this session
    """
    doc: PaymentModel

    def __init__(self, document=None):
        super().__init__(document)
        self._add_handlers()

    def _add_handlers(self):
        async def check_pending_model_handler(payment: PaymentModel):
            """Dependency Injection: Check if this payment is now pending."""
            # 1: Update the timestamp
            payment.doc.last_updated = datetime.now(timezone.utc)

            # 2: Check if the payment is now pending
            if payment.state == PaymentState.PENDING:
                # Fetch assigned session
                await payment.fetch_all_links()
                fast_mqtt.publish(
                    f'/stations/{payment.assigned_session.assigned_station.callsign}/payment/{payment.price}')

            await payment.doc.save_changes()

        PaymentModel.check_pending = check_pending_model_handler

    @classmethod
    async def create(cls, session: SessionModel):
        """Creates a payment document in the database

        Args:
            - self [Payment]: The payment Entity

        Returns:
            Payment

        Raises:
            -

        Example:
            >>> payment.create()
            Payment
        """
        instance = cls()
        await Session(session).calc_durations()
        price = await instance.current_price(session=session)
        instance.doc = PaymentModel(
            assigned_station=session.assigned_station,
            assigned_session=session,
            state=PaymentState.SCHEDULED,
            last_updated=datetime.now(timezone.utc),
            price=price,
        )
        await instance.doc.insert()
        return instance

    async def current_price(self, session: SessionModel) -> Optional[int]:
        """Gets the current (realtime) price of a session

        Args:
            - self [Payment]: The Payment Entity

        Returns:
            int

        Raises:
            -

        Example:
            >>> payment.current_price()
            233
        """
        await session.fetch_all_links()
        locker: Locker = Locker(session.assigned_locker)

        locker_type: LockerType = next(
            (lt for lt in LOCKER_TYPES if lt.name == locker.locker_type), None)

        pricing_model: PricingModel = locker_type.pricing_model

        calculated_price: int = pricing_model.rate_minute * \
            (session.active_duration.total_seconds() / 60)

        # Assure that price is withing boundss
        calculated_price = min(
            max(calculated_price,
                pricing_model.base_fee), 10000)

        return calculated_price
