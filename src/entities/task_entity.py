"""This module provides utilities for  database for tasks."""

# Basics
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio
import os

# Beanie
from beanie.operators import Set
from beanie import SortDirection

# Entities
from src.entities.entity_utils import Entity
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.payment_entity import Payment

# Models
from src.models.station_models import StationModel, TerminalStates
from src.models.session_models import SessionModel, SessionStates
from src.models.task_models import TaskItemModel, TaskStates, TaskTypes

# Services
from src.services.logging_services import logger
from src.services.exceptions import ServiceExceptions


class Task(Entity):
    """Add behaviour to a task Model."""

    def __init__(self, document=None):
        """By default, an entity takes a Beanie document as its model on initialization"""
        super().__init__()
        self.document = document

    @classmethod
    async def create(cls,
                     task_type: TaskTypes,
                     station: StationModel,
                     session: SessionModel,
                     queued_state: SessionStates,
                     timeout_states: List[SessionStates],
                     has_queue: bool = False,
                     ):
        """Create a new task item and insert it into the database.
        :param session_id: The session assigned to this task
        :param station_id: The station assigned to the session
        :param queued)state: The next state the session will have after queue activation
        :param timeout_state: The state the session will have after expiring once.
        """
        instance = cls()
        instance.document = TaskItemModel(
            task_type=task_type,
            assigned_session=session,
            assigned_station=station,
            task_state=TaskStates.QUEUED,
            queued_state=queued_state,
            timeout_states=timeout_states,
            created_at=datetime.now(),
            queue_enabled=has_queue

        )
        await instance.document.insert()
        logger.debug(f"Created task '{instance.document.id}' of {
                     task_type} for session '{session.id}'.")

        # If queueing is disabled, instantly activate the task
        if not has_queue:
            await instance.activate()
        elif await instance.is_next_in_queue:
            await instance.activate()

        return instance

    @classmethod
    async def find(
        cls,
        call_sign: Optional[str] = None,
        task_type: Optional[TaskTypes] = None,
        task_state: Optional[TaskStates] = None,
        assigned_session: Optional[SessionModel] = None,
        assigned_station: Optional[StationModel] = None,
        locker_index: Optional[int] = None
    ):
        """Get a task at a station."""
        instance = cls()

        query = {
            TaskItemModel.assigned_station.call_sign: call_sign,   # pylint: disable=no-member
            TaskItemModel.task_type: task_type,
            TaskItemModel.task_state: task_state,
            TaskItemModel.assigned_session: assigned_session,
            TaskItemModel.assigned_station: assigned_station,
            TaskItemModel.assigned_session.assigned_locker.station_index: locker_index  # pylint: disable=no-member
        }

        # Filter out None values
        query = {k: v for k, v in query.items() if v is not None}

        task_item: TaskItemModel = await TaskItemModel.find(
            query, fetch_links=True
        ).sort((TaskItemModel.created_at, SortDirection.DESCENDING)).first_or_none()

        if task_item:
            instance.document = task_item
            return instance

    @property
    async def is_next_in_queue(self) -> bool:
        """Check whether this task is next in queue"""
        # 1: Find the next queued session item
        next_item: Optional[TaskItemModel] = await TaskItemModel.find(
            TaskItemModel.assigned_station.id == self.assigned_station.id,  # pylint: disable=no-member
            TaskItemModel.task_state == TaskStates.QUEUED,
            fetch_links=True
        ).sort((TaskItemModel.created_at, SortDirection.DESCENDING)).first_or_none()

        if not next_item:
            logger.info("No queued session at station '%s'.",
                        self.assigned_station.id)
            return None

        is_next = next_item.id == self.id

        if is_next:
            logger.debug(
                f"Session '{next_item.assigned_session.id}' identified as next in queue at station '{
                    self.id}'."
            )
        return is_next

    ### State management ###

    async def set_state(self, new_state: TaskStates):
        """Set the state of this task item."""
        await self.document.update(Set({TaskItemModel.task_state: new_state}))

    ### Session runner ###

    async def activate(self) -> None:
        """Activate the assigned session and set this queue item as completed."""
        # 1: Move the session to the next state
        session: Session = Session(self.document.assigned_session)

        if self.document.task_type == TaskTypes.USER:
            await session.set_state(self.document.queued_state)

        # 2: Calculate the timeout timestamp
        timeout_window = session.session_state.value['timeout_secs']
        timeout_date: datetime = self.document.created_at + \
            timedelta(seconds=timeout_window)

        # 5: Update queue item
        await self.document.update(Set({
            TaskItemModel.task_state: TaskStates.PENDING,
            TaskItemModel.activated_at: datetime.now(),
            TaskItemModel.expires_at: timeout_date,
            TaskItemModel.expiration_window: timeout_window
        }))

        # 3: If the session is pending verification, update the terminal state
        if session.session_state == SessionStates.VERIFICATION:
            station: Station = Station(session.assigned_station)
            await station.set_terminal_state(terminal_state=TerminalStates.VERIFICATION)

        # 4: If the session is pending payment, activate it
        if session.session_state == SessionStates.PAYMENT and self.document.task_state == TaskStates.PENDING:
            payment: Payment = await Payment.fetch(session=session.document)
            station: Station = Station(session.assigned_station)
            await station.set_terminal_state(terminal_state=TerminalStates.PAYMENT)
            await payment.get_price()
            # await payment.set_state(PaymentStates.PENDING)

        # 6: Get the expiration time depending on queue type
        if self.document.task_type != TaskTypes.USER:
            timeout_window = os.getenv("STATION_EXPIRATION")

        # 4: Create an expiration handler
        asyncio.create_task(self.register_timeout(
            secs_to_timeout=int(timeout_window)
        ))

    async def register_timeout(self,
                               secs_to_timeout: int):
        """Register an expiration handler. This waits until the expiration duration
        has passed and then fires up the expiration handler."""
        logger.debug(f"Task '{self.document.id}' will time out in {
            secs_to_timeout} seconds."
        )

        # 1 Register the expiration handler
        await asyncio.sleep(int(secs_to_timeout))

        # 2: After the expiration time, fire up the expiration handler if requred
        await self.document.sync()
        if self.document.task_state == TaskStates.PENDING:
            await self.handle_expiration()

    async def handle_expiration(self) -> None:
        """Checks whether the session has entered a state where the user needs to conduct an
        action within a limited time. If that time has been exceeded but the action has not been
        completed, the session has to be expired and the user needs to request a new one
        """
        # 1: Set Session and queue state to expired
        session: Session = Session(self.document.assigned_session)

        # 3: Set the queue state of this item to expired
        await self.set_state(TaskStates.EXPIRED)

        # 4: Update the session state and create a new queue item
        await session.set_state(self.timeout_states[0], True)

        # 5: End the queue flow here if the session has expired or is stale.
        if session.session_state in [SessionStates.EXPIRED, SessionStates.STALE]:
            logger.info(
                ServiceExceptions.SESSION_EXPIRED,
                session=session.id,
                detail=session.session_state,
            )
            return

        # 6: If there is no additional timeout state, end the queue process here
        if len(self.timeout_states) == 1:
            return

        # 7: Else, create new one
        await Task().create(
            task_type=self.document.task_type,
            station=session.assigned_station,
            session=session.document,
            queued_state=self.queued_state,
            timeout_states=self.document.timeout_states[1:],
            has_queue=self.document.queue_enabled)
