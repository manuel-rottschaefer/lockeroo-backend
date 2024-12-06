"""This module provides utilities for  database for tasks."""

# Basics
from typing import List, Optional
from datetime import datetime, timedelta
from asyncio import sleep, create_task
import os
from datetime import datetime, timedelta
from typing import List, Optional


# Beanie
from beanie.operators import Set
from beanie import PydanticObjectId as ObjId
from beanie import SortDirection

# Entities
from src.entities.entity_utils import Entity
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.models.session_models import SessionModel, SessionStates, SESSION_STATE_TIMEOUTS
# Models
from src.models.station_models import StationModel, TerminalStates
from src.models.task_models import TaskItemModel, TaskStates, TaskTypes
from src.services.exception_services import ServiceExceptions
# Services
from src.services.logging_services import logger


class Task(Entity):
    """Add behaviour to a task Model."""
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
            created_ts=datetime.now(),
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
        assigned_session: Optional[ObjId] = None,
        assigned_station: Optional[ObjId] = None,
        locker_index: Optional[int] = None
    ):
        """Get a task at a station."""
        instance = cls()

        query = {
            TaskItemModel.assigned_station.call_sign: call_sign,  # pylint: disable=no-member
            TaskItemModel.task_type: task_type,
            TaskItemModel.task_state: task_state,
            TaskItemModel.assigned_session.id: assigned_session,  # pylint: disable=no-member
            TaskItemModel.assigned_station.id: assigned_station,  # pylint: disable=no-member
            TaskItemModel.assigned_session.assigned_locker.station_index: locker_index  # pylint: disable=no-member
        }

        # Filter out None values
        query = {k: v for k, v in query.items() if v is not None}
        task_item: TaskItemModel = await TaskItemModel.find(
            query, fetch_links=True
        ).sort((TaskItemModel.created_ts, SortDirection.DESCENDING)).first_or_none()

        if task_item:
            instance.document = task_item
        return instance

    @property
    def exists(self) -> bool:
        return self.document is not None

    @property
    async def is_next_in_queue(self) -> bool:
        """Check whether this task is next in queue"""
        # 1: Find the next queued session item
        next_item: Optional[TaskItemModel] = await TaskItemModel.find(
            TaskItemModel.assigned_station.id == self.assigned_station.id,  # pylint: disable=no-member
            TaskItemModel.task_state == TaskStates.QUEUED,
            fetch_links=True
        ).sort((TaskItemModel.created_ts, SortDirection.DESCENDING)).first_or_none()

        if not next_item:
            logger.info("No queued session at station '%s'.",
                        self.assigned_station.id)
            return None

        is_next = next_item.id == self.id

        if is_next:
            logger.debug(
                f"Task '{next_item.id}' identified as next in queue at station '{
                    self.id}'."
            )
        return is_next

    ### State management ###

    async def set_state(self, new_state: TaskStates):
        """Set the state of this task item."""
        await self.document.update(Set({TaskItemModel.task_state: new_state}))

    ### Session runner ###

    def get_timeout_window(self):
        """Get the timeout window in seconds from the config file."""
        timeout_window = 0
        if self.document.task_type == TaskTypes.USER:
            timeout_window = SESSION_STATE_TIMEOUTS.get(
                self.document.queued_state, 0)

        elif self.document.task_type in [TaskTypes.TERMINAL, TaskTypes.LOCKER]:
            timeout_window = int(os.getenv("STATION_EXPIRATION"))

        logger.debug(f"Task '{self.document.id}' will time out to {self.document.timeout_states[0]} in {
            timeout_window} seconds."
        )
        return timeout_window

    async def activate(self) -> None:
        """Call the correct activation handler based on task type."""
        # 2: Get the timeout window for terminal confirmation
        timeout_window = self.get_timeout_window()
        timeout_date: datetime = self.document.created_ts + \
            timedelta(seconds=timeout_window)

        if self.document.task_type == TaskTypes.USER:
            session: Session = Session(self.document.assigned_session)
            if self.document.queued_state:
                await session.set_state(self.document.queued_state)
                await session.save_changes(notify=True)

        if self.document.task_type == TaskTypes.TERMINAL:
            station: Station = Station(self.document.assigned_station)
            await station.document.update(Set({
                StationModel.terminal_state: TerminalStates.VERIFICATION}),
                skip_actions=['notify_station_state'])

        # 3: Update task item
        await self.document.update(Set({
            TaskItemModel.task_state: TaskStates.PENDING,
            TaskItemModel.activated_at: datetime.now(),
            TaskItemModel.expires_at: timeout_date,
            TaskItemModel.expiration_window: timeout_window
        }))

        await restart_expiration_manager()

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
        await session.set_state(self.timeout_states[0])

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

        # 8: Save changes
        await session.save_changes(notify=True)
        await self.save_changes()


async def expiration_manager_loop():
    """Handle expirations."""
    # 1: Get time to next expiration
    next_expiring_task = await TaskItemModel.find(
        TaskItemModel.task_state == TaskStates.PENDING
    ).sort((TaskItemModel.expires_at, SortDirection.ASCENDING)).limit(1).first_or_none()
    if not next_expiring_task:
        return

    next_expiration: datetime = next_expiring_task.expires_at

    # 2: Wait until the task expired
    await sleep((next_expiration - datetime.now()).total_seconds())

    # 3: Check if the task is still pending, then fire up the expiration handler
    if next_expiring_task.task_state == TaskStates.PENDING:
        await Task(next_expiring_task).handle_expiration()


async def restart_expiration_manager():
    """Restart the expiration manager."""
    EXPIRATION_MANAGER.cancel()
    await start_expiration_manager()


async def start_expiration_manager():
    """Start the expiration manager."""
    global EXPIRATION_MANAGER  # pylint: disable=global-statement
    EXPIRATION_MANAGER = create_task(expiration_manager_loop())


EXPIRATION_MANAGER = None
