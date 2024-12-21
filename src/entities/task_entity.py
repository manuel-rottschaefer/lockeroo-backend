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
from src.models.session_models import SessionModel, SessionStates, SESSION_TIMEOUTS
# Models
from src.models.station_models import StationModel, TerminalStates
from src.models.locker_models import LockerModel, LockerStates
from src.models.task_models import TaskItemModel, TaskStates, TaskType, TaskTarget
# Services
from src.services.logging_services import logger


class Task(Entity):
    """Add behaviour to a task Model."""
    document: TaskItemModel

    @classmethod
    async def create(cls,
                     task_target: TaskTarget,
                     task_type: TaskType,
                     session: SessionModel,
                     queued_state: Optional[SessionStates],
                     timeout_states: List[SessionStates],
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
            target=task_target,
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
        logger.debug(
            (f"Created task '#{instance.document.id}' "
             f"of {task_type} for session '#{session.id}'."))

        # TODO: Only Terminal Tasks of type confirmation are queued
        if task_target == TaskTarget.TERMINAL and task_type == TaskType.CONFIRMATION:
            if await instance.is_next_in_queue:
                await instance.activate()
        else:
            await instance.activate()

        return instance

    @classmethod
    # TODO: Do we even need these find methods at all?
    async def find(
        cls,
        task_type: Optional[TaskType] = 'unset',
        task_target: Optional[TaskTarget] = 'unset',
        task_state: Optional[TaskStates] = 'unset',
        assigned_session: Optional[ObjId] = 'unset',
        station_callsign: Optional[str] = 'unset',
        assigned_station: Optional[ObjId] = 'unset',
        assigned_locker: Optional[ObjId] = 'unset',
        # TODO: Check data type here
        queued_state: Optional[Union[SessionStates, TerminalStates]] = 'unset',
    ):
        """Get a task at a station."""
        instance = cls()

        query = {
            TaskItemModel.task_type: task_type,
            TaskItemModel.target: task_target,
            TaskItemModel.task_state: task_state,
            TaskItemModel.assigned_session.id: assigned_session,  # pylint: disable=no-member
            TaskItemModel.assigned_station.id: assigned_station,  # pylint: disable=no-member
            TaskItemModel.assigned_station.callsign: station_callsign,  # pylint: disable=no-member
            TaskItemModel.assigned_locker.id: assigned_locker,  # pylint: disable=no-member
            TaskItemModel.queued_session_state: queued_state,
        }

        # Filter out None values
        query = {k: v for k, v in query.items() if v != 'unset'}
        task_item: TaskItemModel = await TaskItemModel.find(
            query, fetch_links=True
        ).sort((TaskItemModel.created_ts, SortDirection.DESCENDING)).first_or_none()

        if task_item:
            instance.document = task_item
        return instance

    async def pop_queue(
        self,
            station: StationModel) -> Optional[TaskItemModel]:
        """Get the next task in queue at a station."""
        # Find the next task in queue or pending task
        next_task = await TaskItemModel.find(
            TaskItemModel.assigned_station.id == station.id,  # pylint: disable=no-member
            TaskItemModel.target == TaskTarget.TERMINAL,
            # TaskItemModel.task_type == TaskType.REPORT,
            In(TaskItemModel.task_state,
                [TaskStates.PENDING, TaskStates.QUEUED]),
            TaskItemModel.assigned_locker == None,  # pylint: disable=singleton-comparison
            fetch_links=True
        ).sort(
            (TaskItemModel.created_ts, SortDirection.ASCENDING)
        ).first_or_none()

        # If the next task is pending, return None
        if next_task is not None and next_task.task_state == TaskStates.PENDING:
            logger.info(
                (f"Not proceeding with queue activation, "
                 f"Task '#{next_task.id}' is still pending."))
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
            station=self.assigned_station)
        if next_task is None:
            return False

        if is_next := next_task.id == self.id:
            logger.debug(
                f"Task '#{next_task.id}' identified as next in queue at station '{
                    self.id}'."
            )
        return is_next

    ### State mapper ###
    def map_session_to_terminal_state(self, session_state: SessionStates) -> Optional[TerminalStates]:
        """Map session states to task states."""
        # TODO: This is a suboptimal solution, refactor this
        STATE_MAP = {  # pylint: disable=invalid-name
            SessionStates.PAYMENT_SELECTED: TerminalStates.VERIFICATION,
            SessionStates.ACTIVE: TerminalStates.PAYMENT
        }
        if session_state in STATE_MAP:
            return STATE_MAP.get(session_state)

    ### Session runner ###

    def get_timeout_window(self, session_state):
        """Get the timeout window in seconds from the config file."""
        timeout_window = 0
        if self.document.target == TaskTarget.USER:
            timeout_window = int(os.getenv("USER_EXPIRATION", '300'))
        elif self.document.target in {TaskTarget.TERMINAL, TaskTarget.LOCKER}:
            if self.document.task_type == TaskType.CONFIRMATION:
                timeout_window = int(os.getenv("STATION_EXPIRATION", '10'))
            else:
                timeout_window = SESSION_TIMEOUTS.get(session_state)
        else:
            timeout_window = SESSION_TIMEOUTS.get(
                session_state)  # Default case if no match found

        assert timeout_window, f"No timeout window found for task '#{
            self.document.id}'."

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

        # logger.debug(
        #    (f"Task '#{self.document.id}' will time out to "
        #     f"{self.document.timeout_states[0]} in {timeout_window} seconds."))

        # If the task awaited a report, advance the session state
        if self.document.task_type == TaskType.REPORT:
            # Advance session to next state
            if self.document.queued_session_state:
                session.document.session_state = self.document.queued_session_state
                await session.document.save_changes()

        elif self.document.task_type == TaskType.CONFIRMATION:
            # Check if the task is awaiting confirmation from terminal or locker
            if self.document.target in TaskTarget.TERMINAL:
                # Instruct the station to enable the terminal
                station: Station = Station(self.document.assigned_station)
                await station.sync()
                assert (station.document.terminal_state == TerminalStates.IDLE
                        ), f"Terminal of station '#{station.document.id}' is not idle."
                if terminal_state := self.map_session_to_terminal_state(session.session_state):
                    station.document.instruct_terminal_state(terminal_state)
            elif self.document.target == TaskTarget.LOCKER:
                # Instruct the locker to unlock
                locker: Locker = Locker(self.document.assigned_locker)
                assert (locker.document.reported_state == LockerStates.LOCKED
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
        if self.document.target == TaskTarget.TERMINAL and self.document.task_type == TaskType.REPORT:
            next_task = Task(await self.pop_queue(
                station=self.document.assigned_station))
            if next_task.exists:
                logger.debug(
                    f"Task completed, Task '#{next_task.id}' is next at station.")
                await next_task.activate()

    async def handle_expiration(self) -> None:
        """Handle the expiration of a task item."""
        # 1: Register Task Expiration
        await self.document.sync()
        assert (self.document.task_state == TaskStates.PENDING
                ), f"Task '#{self.id}' is not pending."
        self.document.task_state = TaskStates.EXPIRED

        # 2: Update the session state to its timeout state
        await self.document.fetch_link(TaskItemModel.assigned_session)

        assert len(self.timeout_states), f"No timeout states defined for task '#{
            self.id}'."
        self.document.assigned_session.session_state = self.timeout_states[0]

        # 3: Save changes
        await self.document.save_changes()
        await self.document.assigned_session.save_changes()

        # 5: End the queue flow here if the session has timed out or no additional timeout states
        TIMEOUT_STATES = [SessionStates.EXPIRED,
                          SessionStates.ABORTED, SessionStates.STALE]
        if self.document.assigned_session.session_state in TIMEOUT_STATES or len(self.timeout_states) == 1:
            # Restart the expiration manager
            await restart_expiration_manager()
            return

        # 7: Else, create a new task item for the next timeout state
        await Task().create(
            task_target=self.document.target,
            task_type=self.document.task_type,
            station=self.document.assigned_session.assigned_station,
            session=self.document,
            queued_state=self.document.queued_session_state,
            timeout_states=self.document.timeout_states[1:])


async def expiration_manager_loop():
    """Handle expirations."""
    # 1: Get time to next expiration
    next_expiring_task: TaskItemModel = await TaskItemModel.find(
        TaskItemModel.task_state == TaskStates.PENDING
    ).sort(
        (TaskItemModel.expires_at, SortDirection.ASCENDING)
    ).first_or_none()
    if next_expiring_task is None:
        # logger.debug(
        #    "No pending tasks found, task expiration manager is now idle.")
        return

    # 2: Wait until the task expired
    await sleep(
        (next_expiring_task.expires_at - datetime.now()
         ).total_seconds())

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
