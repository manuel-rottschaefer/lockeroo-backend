"""This module provides utilities for  database for tasks."""

# Basics
from typing import List, Optional, Union
from datetime import datetime, timedelta
from asyncio import sleep, create_task
import os

# Beanie
from beanie import PydanticObjectId as ObjId, SortDirection
from beanie.operators import In

# Entities
from src.entities.entity_utils import Entity
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.locker_entity import Locker
from src.models.session_models import SessionModel, SessionStates, SESSION_STATE_TIMEOUTS
# Models
from src.models.station_models import StationModel, TerminalStates
from src.models.locker_models import LockerModel, LockerStates
from src.models.task_models import TaskItemModel, TaskStates, TaskTypes
# Services
from src.services.logging_services import logger


class Task(Entity):
    """Add behaviour to a task Model."""
    document: TaskItemModel

    @classmethod
    async def create(cls,
                     task_type: TaskTypes,
                     session: SessionModel,
                     queued_state: Optional[SessionStates],
                     timeout_states: List[SessionStates],
                     has_queue: bool = False,
                     station: Optional[StationModel] = None,
                     locker: Optional[LockerModel] = None,
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
            assigned_locker=locker,
            task_state=TaskStates.QUEUED,
            queued_session_state=queued_state,
            timeout_states=timeout_states,
            created_ts=datetime.now(),

        )
        await instance.document.insert()
        logger.debug(f"Created task '#{instance.document.id}' of {
                     task_type} for session '{session.id}'.")

        # If queueing is disabled, instantly activate the task
        # TODO: A task is only added to the queue if it is of type terminal
        if not has_queue or task_type != TaskTypes.TERMINAL:
            await instance.activate()
        elif await instance.is_next_in_queue:
            await instance.activate()

        return instance

    @classmethod
    async def find(
        cls,
        task_type: Optional[TaskTypes] = None,
        task_state: Optional[TaskStates] = None,
        assigned_session: Optional[ObjId] = None,
        assigned_station: Optional[ObjId] = None,
        assigned_locker: Optional[ObjId] = None,
        # TODO: Check data type here
        queued_state: Optional[Union[SessionStates, TerminalStates]] = None,
    ):
        """Get a task at a station."""
        instance = cls()

        query = {
            TaskItemModel.task_type: task_type,
            TaskItemModel.task_state: task_state,
            TaskItemModel.assigned_session.id: assigned_session,  # pylint: disable=no-member
            TaskItemModel.assigned_station.id: assigned_station,  # pylint: disable=no-member
            TaskItemModel.assigned_locker.id: assigned_locker,  # pylint: disable=no-member
            TaskItemModel.queued_session_state: queued_state,
        }

        # Filter out None values
        query = {k: v for k, v in query.items() if v is not None}
        task_item: TaskItemModel = await TaskItemModel.find(
            query, fetch_links=True
        ).sort((TaskItemModel.created_ts, SortDirection.DESCENDING)).first_or_none()

        if task_item:
            instance.document = task_item
        return instance

    async def pop_queue(self, station: StationModel, task_type: TaskTypes) -> Optional[TaskItemModel]:
        """Get the next task in queue at a station."""
        # Find the next task in queue or pending task
        next_task = await TaskItemModel.find(
            TaskItemModel.assigned_station.id == station.id,  # pylint: disable=no-member
            In(TaskItemModel.task_state,
                [TaskStates.PENDING, TaskStates.QUEUED]),
            TaskItemModel.task_type == TaskTypes.TERMINAL,
            fetch_links=True
        ).sort((TaskItemModel.task_state == TaskStates.PENDING, SortDirection.DESCENDING),
               (TaskItemModel.created_ts, SortDirection.ASCENDING)).first_or_none()

        # If the next task is pending, return None
        if next_task and next_task.task_state == TaskStates.PENDING:
            logger.warning(
                (f"Not proceeding with queue activation, "
                 f"task {next_task.id} still pending."))
            return None

        # Return the next queued task
        return next_task

    @property
    def exists(self) -> bool:
        return self.document is not None

    @property
    async def is_next_in_queue(self) -> bool:
        """Check whether this task is next in queue"""
        next_task = await self.pop_queue(
            station=self.assigned_station,
            task_type=self.task_type)
        if next_task is None:
            return False

        if is_next := next_task.id == self.id:
            logger.debug(
                f"Task '#{next_task.id}' identified as next in queue at station '{
                    self.id}'."
            )
        return is_next

    ### State mapper ###
    def map_session_to_terminal_state(self, session_state: SessionStates) -> TerminalStates:
        """Map session states to task states."""
        STATE_MAP = {  # pylint: disable=invalid-name
            SessionStates.VERIFICATION: TerminalStates.VERIFICATION,
            SessionStates.PAYMENT: TerminalStates.PAYMENT
        }  # TODO: FIXME this does not work
        return STATE_MAP.get(session_state, TerminalStates.IDLE)

    ### Session runner ###

    def get_timeout_window(self, session_state):
        """Get the timeout window in seconds from the config file."""
        timeout_window = 0
        if self.document.task_type in [TaskTypes.TERMINAL, TaskTypes.LOCKER]:
            timeout_window = SESSION_STATE_TIMEOUTS.get(
                session_state)

        elif self.document.task_type == TaskTypes.USER:
            timeout_window = int(os.getenv("USER_EXPIRATION", '300'))

        elif self.document.task_type == TaskTypes.CONFIRMATION:
            timeout_window = int(os.getenv("STATION_EXPIRATION", '10'))

        return timeout_window

    async def activate(self) -> None:
        """Call the correct activation handler based on task type."""
        # 1: Get the assigned session
        session: Session = Session(self.document.assigned_session)

        # 2: Get the timeout window for terminal confirmation
        window_state: SessionStates = self.document.queued_session_state or session.session_state
        timeout_window = self.get_timeout_window(window_state)
        timeout_date: datetime = self.document.created_ts + \
            timedelta(seconds=timeout_window)

        # 3: Update task item
        self.document.task_state = TaskStates.PENDING
        self.document.activated_at = datetime.now()
        self.document.expires_at = timeout_date
        self.document.expiration_window = timeout_window
        await self.document.save_changes()
        logger.debug(f"Task '#{self.document.id}' will time out to {
            self.document.timeout_states[0]} in {timeout_window} seconds."
        )

        # 4: Call activation handlers
        if self.document.task_type in [
                TaskTypes.TERMINAL, TaskTypes.LOCKER]:
            # Advance session to next state
            if self.document.queued_session_state:
                session.document.session_state = self.document.queued_session_state
                await session.document.save_changes()

        if self.document.task_type == TaskTypes.CONFIRMATION:
            # Check if the task is awaiting confirmation from terminal or locker
            if self.document.assigned_station:
                # Instruct the station to enable the terminal
                station: Station = Station(self.document.assigned_station)
                assert (station.document.terminal_state == TerminalStates.IDLE
                        ), f"Terminal of station '#{station.document.id}' is not idle."
                station.document.instruct_terminal_state(
                    self.map_session_to_terminal_state(await session.next_state))
            elif self.document.assigned_locker:
                # Instruct the locker to unlock
                locker: Locker = Locker(self.document.assigned_locker)
                assert (locker.document.locker_state == LockerStates.LOCKED
                        ), f"Locker {locker.document.id} is not locked."
                await locker.instruct_state(LockerStates.UNLOCKED)

        # 5: Restart the expiration manager
        await restart_expiration_manager()

    async def complete(self) -> None:
        """Complete a task item."""
        # 1: Set the task state to completed
        self.document.task_state = TaskStates.COMPLETED
        self.document.completed_at = datetime.now()
        await self.document.save_changes()

        # 2: If this was a terminal task, enable the next task in queue
        if self.document.task_type == TaskTypes.TERMINAL:
            next_task = await self.pop_queue(
                station=self.document.assigned_station,
                task_type=TaskTypes.TERMINAL)
            if next_task:
                logger.warning(
                    f"Task completed, now next task in queue: {next_task.id}")
                await next_task.activate()

    async def handle_expiration(self) -> None:
        """Handle the expiration of a task item."""
        # 1: Set Session and queue state to expired
        session: Session = Session(self.document.assigned_session)

        # 2: Set the queue state of this item to expired
        self.document.task_state = TaskStates.EXPIRED

        # 3: Update the session state and create a new queue item
        assert len(self.timeout_states), f"No timeout states defined for task '#{
            self.id}'."
        session.document.session_state = self.timeout_states[0]

        # 4: Save changes
        await session.document.save_changes()
        await self.document.save_changes()

        # 5: End the queue flow here if the session has timed out or no additional timeout states
        TIMEOUT_STATES = [SessionStates.EXPIRED, SessionStates.STALE]
        if session.session_state in TIMEOUT_STATES or len(self.timeout_states) == 1:
            return

        # 7: Else, create a new task item for the next timeout state
        await Task().create(
            task_type=self.document.task_type,
            station=session.assigned_station,
            session=session.document,
            queued_state=self.document.queued_session_state,
            timeout_states=self.document.timeout_states[1:])


async def expiration_manager_loop():
    """Handle expirations."""
    # 1: Get time to next expiration
    next_expiring_task = await TaskItemModel.find(
        TaskItemModel.task_state == TaskStates.PENDING
    ).sort(
        (TaskItemModel.expires_at, SortDirection.ASCENDING)
    ).first_or_none()
    if next_expiring_task is None:
        logger.debug(
            "No pending tasks found, task expiration manager is now idle.")
        return

    next_expiration: datetime = next_expiring_task.expires_at

    # 2: Wait until the task expired
    await sleep((next_expiration - datetime.now()).total_seconds())

    # 3: Check if the task is still pending, then fire up the expiration handler
    await next_expiring_task.sync()  # TODO: Is this necessary?
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
