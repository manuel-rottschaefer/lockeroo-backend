"""
    Queue Utils Module
"""

# Basics
from typing import List, Optional
from datetime import datetime
import asyncio
# Beanie
from beanie import PydanticObjectId as ObjId
# Entities
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.payment_entity import Payment
# Models
from src.models.session_models import SessionStates
from src.models.queue_models import QueueItemModel, QueueStates
from src.models.payment_models import PaymentModel, PaymentStates
# Services
from src.services.logging_services import logger
from src.services.exceptions import ServiceExceptions


class QueueItem():
    """Add behaviour to a queue Entity."""

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

    def __init__(self, document: QueueItemModel = None):
        super().__init__()
        self.document = document

    @classmethod
    async def fetch(cls, session_id: ObjId):
        """Get the latest queue item of a session."""
        # 1: Create the instance
        instance = cls()

        # 2: Look for the latest queue item
        queue_item: QueueItemModel = await QueueItemModel.find(
            QueueItemModel.assigned_session == session_id
        ).sort(-QueueItemModel.registered_ts).first_or_none()

        if queue_item:
            instance.document = queue_item
            return instance
        else:
            return None

    @classmethod
    async def create(cls, station_id: ObjId, session_id: ObjId):
        """Create a new queue item and insert it into the database."""
        instance = cls()
        instance.document = QueueItemModel(
            assigned_session=session_id,
            assigned_station=station_id,
            queue_state=QueueStates.QUEUED,
            registered_ts=datetime.now(),
        )
        await instance.document.insert()
        logger.debug(f"Session '{session_id}' added to queue at station '{
                     station_id}'.")

        # Check if the session is next in line
        if await instance.is_next:
            await instance.activate()
        return instance

    @classmethod
    async def get_next_in_line(cls, station_id: ObjId):
        """Create a Queue Item from the next item in the queue."""
        instance = cls()
        # 1: Find the next queued session item
        next_item: Optional[QueueItemModel] = await QueueItemModel.find(
            QueueItemModel.assigned_station == station_id,
            QueueItemModel.queue_state == QueueStates.QUEUED,
        ).sort(QueueItemModel.registered_ts).first_or_none()

        if not next_item:
            logger.info("No queued session at station '%s'.", station_id)
            return None

        instance.document = next_item
        logger.debug(
            f"Identified session '{next_item.assigned_session}' in queue at station '{
                station_id}' as next in line."
        )

        return instance

    @property
    async def is_next(self) -> bool:
        """Check wether this queue item is next in line."""
        next_item = await QueueItem().get_next_in_line(self.document.assigned_station)
        return next_item.id == self.document.id

    @property
    async def session(self) -> Session:
        """Get the session assigned to this queue item."""
        return await Session().fetch(session_id=self.document.assigned_session)

    ### State management ###

    async def set_state(self, new_state: QueueStates):
        """Set the state of this queue item."""
        self.document.queue_state = new_state
        await self.document.replace()

    ### Session runner ###

    async def activate(self) -> None:
        """Activate the assigned session and set this queue item as completed."""
        # 1: Move session into next
        session: Session = await self.session
        await session.set_state(await session.next_state)

        # 2: If the session is pending payment, activate it
        if session.session_state == SessionStates.PAYMENT_PENDING:
            payment: Payment = await Payment.fetch(session_id=session.id)
            await payment.activate()

        # 3: If the session is pending verification, update the terminal state
        station_relevant_states: List[SessionStates] = [
            SessionStates.VERIFICATION_PENDING,
            SessionStates.PAYMENT_PENDING
        ]
        if session.session_state in station_relevant_states:
            station: Station = await Station().fetch(session.assigned_station)
            await station.set_terminal_state(session_state=session.session_state)

        # 3: Set this item as pending
        self.document.queue_state = QueueStates.PENDING
        await self.document.replace()

    async def register_expiration(self, seconds: int, state: SessionStates):
        """Register an expiration handler. This waits until the expiration duration has passed and then fires up the expiration handler."""
        # 1 Register the expiration handler
        await asyncio.sleep(int(seconds))

        # 2: After the expiration time, fire up the expiration handler if requred
        await self.document.sync()
        if self.document.queue_state == QueueStates.PENDING:
            await self.handle_expiration(state)

    async def handle_expiration(self, state: SessionStates) -> None:
        """Checks wether the session has entered a state where the user needs to conduct an
        action within a limited time. If that time has been exceeded but the action has not been
        completed, the session has to be expired and the user needs to request a new one
        """
        # 1: Set Session and queue state to expired
        session: Session = await self.session

        # 2: If this session has already timed out once, expire it now.
        # The user then has to start a new session again.
        if await session.timeout_amount > 0:
            state = SessionStates.EXPIRED

        # 3: Update session and queue item states
        await session.set_state(state, True)
        await self.set_state(QueueStates.EXPIRED)

        # 4: Create a logging message
        logger.info(
            ServiceExceptions.SESSION_EXPIRED,
            session=session.id,
            detail=session.session_state,
        )
