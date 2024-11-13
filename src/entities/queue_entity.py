"""
    Queue Utils Module
"""

# Basics
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio
# Beanie
from beanie import PydanticObjectId as ObjId
from beanie import SortDirection
# Entities
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.payment_entity import Payment
# Models
from src.models.session_models import SessionStates
from src.models.queue_models import QueueItemModel, QueueStates, EXPIRATION_DURATIONS
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
        ).sort((QueueItemModel.created_at, SortDirection.DESCENDING)).first_or_none()

        # logger.debug(f"Latest queue item: '{
        #             queue_item.id}' for session '{session_id}'")

        if queue_item:
            instance.document = queue_item
            return instance
        else:
            return None

    @classmethod
    async def create(cls,
                     station_id: ObjId,
                     session_id: ObjId,
                     queued_state: SessionStates,
                     timeout_state: SessionStates = SessionStates.EXPIRED,
                     skip_eval: bool = False
                     ):
        """Create a new queue item and insert it into the database.
        :param session_id: The session to be queued
        :param station_id: The station assigned to the queued session
        :param queued)state: The next state the session will have after queue activation
        :param timeout_state: The state the session will have after expiring once.
        """
        instance = cls()
        instance.document = QueueItemModel(
            assigned_session=session_id,
            assigned_station=station_id,
            queue_state=QueueStates.QUEUED,
            queued_state=queued_state,
            timeout_state=timeout_state,
            created_at=datetime.now(),
        )
        await instance.document.insert()
        logger.debug(f"Session '{session_id}' added to queue at station '{
                     station_id}'.")

        # Check if the session is next in line
        if skip_eval or await instance.is_next:
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
        ).sort((QueueItemModel.created_at, SortDirection.DESCENDING)).first_or_none()

        if not next_item:
            logger.info("No queued session at station '%s'.", station_id)
            return None

        instance.document = next_item
        logger.debug(
            f"Session '{next_item.assigned_session}' identified as next in queue at station '{
                station_id}'."
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

        # 1: Move the session to the next state
        session: Session = await self.session
        await session.set_state(self.document.queued_state)

        # 2: Calculate the timeout timestamp
        secs_to_expiration = int(EXPIRATION_DURATIONS[session.session_state])
        expiration_date: datetime = self.document.created_at + \
            timedelta(seconds=secs_to_expiration)

        # 2: Update queue item
        self.document.queue_state = QueueStates.PENDING
        self.document.activated_at = datetime.now()
        self.document.expires_at = expiration_date
        self.document.expiration_window = secs_to_expiration
        self.document.replace()
        await self.document.replace()

        # 3: If the session is pending verification, update the terminal state
        station_relevant_states: List[SessionStates] = [
            SessionStates.VERIFICATION,
            SessionStates.PAYMENT
        ]
        if session.session_state in station_relevant_states:
            station: Station = await Station().fetch(session.assigned_station)
            await station.set_terminal_state(session_state=session.session_state)

        # 3: If the session is pending payment, activate it
        if session.session_state == SessionStates.PAYMENT:
            payment: Payment = await Payment.fetch(session_id=session.id)
            try:
                await payment.activate()
            except Exception as e:
                print(e)

        # 4: Create an expiration handler
        asyncio.create_task(self.register_expiration(
            seconds_to_expiration=int(
                EXPIRATION_DURATIONS[session.session_state]),
            timeout_state=self.document.timeout_state
        ))

    async def register_expiration(self,
                                  seconds_to_expiration: int,
                                  timeout_state: SessionStates):
        """Register an expiration handler. This waits until the expiration duration has passed and then fires up the expiration handler."""
        logger.debug(f"Session '{self.assigned_session}' will expire in {
                     seconds_to_expiration} seconds.")

        # 1 Register the expiration handler
        await asyncio.sleep(int(seconds_to_expiration))

        # 2: After the expiration time, fire up the expiration handler if requred
        await self.document.sync()
        if self.document.queue_state == QueueStates.PENDING:
            await self.handle_expiration(timeout_state)

    async def handle_expiration(self, state: SessionStates) -> None:
        """Checks wether the session has entered a state where the user needs to conduct an
        action within a limited time. If that time has been exceeded but the action has not been
        completed, the session has to be expired and the user needs to request a new one
        """
        logger.debug(f"Session '{self.assigned_session}' expired.")
        # 1: Set Session and queue state to expired
        session: Session = await self.session

        # 2: If this session has already timed out once, expire it now.
        # The user then has to start a new session again.
        # if await session.timeout_amount > 0:
        #    state = SessionStates.EXPIRED

        # 3: Set the queue state of this item to expired
        await self.set_state(QueueStates.EXPIRED)

        # 4: Update the session state and create a new queue item
        await session.set_state(state, True)

        # 5: End the queue flow here if the session has expired or is stale.
        if state in [SessionStates.EXPIRED, SessionStates.STALE]:
            logger.info(
                ServiceExceptions.SESSION_EXPIRED,
                session=session.id,
                detail=session.session_state,
            )
            return

        # 6: Otherwise, create a new queue item
        await QueueItem().create(
            station_id=session.assigned_station,
            session_id=session.id,
            queued_state=self.queued_state,
        )
