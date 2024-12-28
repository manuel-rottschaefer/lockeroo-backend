"""This module provides utilities for  database for tasks."""
# Basics
from asyncio import create_task, sleep
from datetime import datetime, timedelta
from os import getenv
from typing import Optional

# Beanie
from beanie import Link, SortDirection
from beanie.operators import In

# Entities
from src.entities.entity_utils import Entity
from src.entities.locker_entity import Locker
from src.entities.session_entity import Session
from src.models.locker_models import LockerState
from src.models.session_models import (
    ACTIVE_SESSION_STATES,
    FOLLOW_UP_STATES,
    SESSION_TIMEOUTS,
    SessionModel,
    SessionState)
# Models
from src.models.station_models import TerminalState
from src.models.task_models import (TaskItemModel, TaskState, TaskTarget,
                                    TaskType)
from src.services.logging_services import logger
# Services
from src.services.mqtt_services import fast_mqtt


class Task(Entity):
    """Add behaviour to a task Model."""
    doc: TaskItemModel

    ### Properties ###
    @property
    def timeout_window(self) -> int:
        """Get the timeout window of the specified task.
        Finds the timeout window in seconds depending on the task context.

        Args:
            self (Task): The own task entity

        Returns:
            int: The timeout window in seconds
        """
        assert self.doc.target is not None, f"No target found for task '#{
            self.doc.id}'."

        if self.doc.target in [TaskTarget.USER, TaskTarget.LOCKER]:
            timeout_window = SESSION_TIMEOUTS.get(
                self.doc.assigned_session.session_state, 0)
        elif self.doc.target == TaskTarget.TERMINAL:
            timeout_window = int(getenv("STATION_EXPIRATION", '10'))
        else:
            timeout_window = 0
        return timeout_window

    @property
    def exists(self) -> bool:
        """Check if the task exists."""
        return self.doc is not None

    ### Class methods ###
    @classmethod
    async def from_next_queued(cls, station_id: str) -> Optional['Task']:
        """Get the next task in queue.
        Find the next task in queue at a specified station, if any.
        If the task is not already pending, return it.

        Args:
            station_id (str): The ID of the station to get the next task from

        Returns:
            Optional[Task]: The next task in queue, if any
        """
        # 1: Check if there is a pending task at the station
        if await TaskItemModel.find(
            TaskItemModel.assigned_station.id == station_id,  # pylint: disable=no-member
            TaskItemModel.target == TaskTarget.TERMINAL,
            TaskItemModel.task_state == TaskState.PENDING,
            fetch_links=True
        ).count() > 0:
            return Task()

        # 2: Get the next task in queue
        task_item = await TaskItemModel.find(
            TaskItemModel.assigned_station.id == station_id,  # pylint: disable=no-member
            TaskItemModel.target == TaskTarget.TERMINAL,
            TaskItemModel.task_state == TaskState.QUEUED,
            fetch_links=True
        ).sort(
            (TaskItemModel.created_at, SortDirection.ASCENDING)
        ).first_or_none()

        return cls(task_item)

    ### Queue utilities###
    async def evaluate_queue_state(self) -> int:
        """ Evaluate the position of this task in the station queue.
        First, check if the task is a terminal task, then get the position of the task in the queue.
        If the task is not a terminal task, or next in queue, activate it immediately.
        Finally, return the position of the task in the queue.

        Args:
            self (Task): The own task entity

        Returns:
            int: The position of the task in the queue
        """

        # Get the position of the task in the queue
        await self.doc.fetch_link(TaskItemModel.assigned_station)
        queue_pos = await TaskItemModel.find(
            TaskItemModel.assigned_station.id == self.doc.assigned_station.id,  # pylint: disable=no-member
            TaskItemModel.target == TaskTarget.TERMINAL,
            In(TaskItemModel.task_state, [
               TaskState.QUEUED, TaskState.PENDING]),
            TaskItemModel.created_at < self.doc.created_at
        ).count() + 1
        # logger.debug(
        #    (f"Task '#{self.doc.id}' is #{queue_pos} in the queue at station "
        #     f"'{self.doc.assigned_station.callsign}'."))

        self.doc.assigned_session.queue_position = queue_pos
        await self.doc.save_changes(skip_actions=['log_state_change'])

        # Tasks that are not terminal tasks are activated immediately
        if self.target != TaskTarget.TERMINAL or queue_pos == 1:
            await self.activate()

        return queue_pos

    async def instruct_terminal_state(self, session_state: SessionState) -> None:
        """Apply a session state to the terminal.
        Check if the assigned session is a link, then fetch it.
        If the session state is in the state map, send the state instruction to the terminal."""
        # Check if assigned station is not a link anymore
        if not isinstance(self.assigned_session, Link):
            await self.doc.fetch_link(TaskItemModel.assigned_station)
        STATE_MAP = {  # pylint: disable=invalid-name
            SessionState.PAYMENT_SELECTED: TerminalState.VERIFICATION,
            SessionState.ACTIVE: TerminalState.PAYMENT
        }
        if session_state in STATE_MAP:
            logger.debug(
                (f"Sending {STATE_MAP[session_state]} instruction to "
                 f"terminal at station '#{self.doc.assigned_station.callsign}'."))
            fast_mqtt.publish(
                message_or_topic=f"stations/{
                    self.doc.assigned_station.callsign}/terminal/instruct",
                payload=STATE_MAP[session_state].upper(),
                qos=2)
        else:
            logger.debug(
                f"No state instruction for session state '{session_state}' of task '#{self.doc.id}'.")

    async def activate(self) -> None:
        """Activate a task item.

        When a task is activated, it awaits a confirmation or report from an entity in a specified
        timeframe after sending out instructions or moving the assigned session to the next state.
        If no such response occurs within the timeout window, the task expires.

        Calculates the time to expiration, then initiates activites depending on the task context,
        then finally restarts the task expiration manager.

        Args:
            self (Task): The own task entity

        Returns:
            None

        Raises:
            AssertionError
        """
        # 1: Check if the task is actually queued, then get the assigned session
        assert (self.doc.task_state == TaskState.QUEUED
                ), f"Task '#{self.doc.id}' is not queued."
        session: Session = Session(self.doc.assigned_session)

        # 2: Get the timeout window for terminal confirmation
        timeout_window = self.timeout_window
        timeout_date: datetime = datetime.now() + timedelta(seconds=timeout_window)

        # 3: Update the task item
        self.doc.task_state = TaskState.PENDING
        self.doc.activated_at = datetime.now()
        self.doc.expires_at = timeout_date
        self.doc.expiration_window = timeout_window
        await self.doc.save_changes()
        # logger.debug(
        #    (f"Task '#{self.doc.id}' will time out to "
        #     f"{self.doc.timeout_states[0]} in {timeout_window} seconds."))

        # 4: If the task awaits a user report, advance the session state
        if self.doc.task_type == TaskType.REPORT and self.doc.moves_session:
            session.doc.session_state = FOLLOW_UP_STATES[session.doc.session_state]
            await session.doc.save_changes()

        # If the task awaits a state confirmation from a station terminal, send a state instruction.
        elif self.doc.task_type == TaskType.CONFIRMATION and self.doc.target == TaskTarget.TERMINAL:
            await self.instruct_terminal_state(session.session_state)

        # If the task awaits a locker unlocking confirmation, send an unlock instruction
        elif self.doc.task_type == TaskType.CONFIRMATION and self.doc.target == TaskTarget.LOCKER:
            await self.doc.fetch_link(TaskItemModel.assigned_locker)
            locker: Locker = Locker(self.doc.assigned_locker)
            assert (locker.doc.reported_state == LockerState.LOCKED
                    ), f"Locker {locker.doc.id} is not locked."
            await locker.instruct_state(LockerState.UNLOCKED)

        # 5: Restart the expiration manager
        task_expiration_manager.restart()

    async def complete(self) -> None:
        """Complete a task item.

        Checks if the task is still queued and should not have expired,
        then updates it to COMPLETED and if the task completed as a result of a station
        terminal reporting IDLE, activates the next task at that station.

        Args:
            self (task): Own task Entity

        Returns:
            None

        Raises:
            AssertionError: If the task is not pending or should have expired already
        """
        # 1: Sync the task and check if its still pending
        await self.doc.sync()
        assert (self.doc.task_state == TaskState.PENDING
                ), f"Cannot complete Task '#{self.doc.id}' as it is in {self.doc.task_state}."
        assert (datetime.now() < self.doc.expires_at + timedelta(seconds=1)
                ), f"Cannot complete Task '#{self.doc.id}' as it should already have timed out."

        # 2: Update the task to completed
        self.doc.task_state = TaskState.COMPLETED
        self.doc.completed_at = datetime.now()
        await self.doc.save_changes()

        # 3: Restart the expiration manager
        task_expiration_manager.restart()

        # 4: If the stations terminal is not idle, end here
        await self.doc.fetch_link(TaskItemModel.assigned_station)
        await self.doc.assigned_station.sync()
        if self.doc.assigned_station.terminal_state != TerminalState.IDLE:
            return

        # 5: Else, start the next task
        next_task: Task = await Task.from_next_queued(
            station_id=self.doc.assigned_station.id)
        if next_task.exists:
            await next_task.activate()

    async def handle_expiration(self) -> None:
        """Handle the expiration of a task item.
        Checks if the task is still pending, then sets it to expired and updates the session state
        to the next timeout state in the task's timeout states list.
        Finally, restarts the expiration manager.

        Args:
            self (Task): The own task entity

        Returns:
            None

        Raises:
            AssertionError: If the task is not pending or has no timeout states defined
        """
        # 1: Refresh task document
        await self.doc.sync()

        # 2: If task is still pending, set it to expired
        assert (self.doc.task_state == TaskState.PENDING
                ), f"Task '#{self.id}' is not pending."
        self.doc.task_state = TaskState.EXPIRED

        # 3: Update the session state to its timeout state
        await self.doc.fetch_link(TaskItemModel.assigned_session)
        session: SessionModel = self.doc.assigned_session
        assert len(self.timeout_states
                   ), f"No timeout states defined for task '#{self.id}'."
        session.session_state = self.timeout_states[0]

        # 4: Save changes
        await self.doc.save_changes()
        await session.save_changes()

        # 5: End the queue flow here if the session has timed out or no additional timeout states
        print(session.session_state, self.doc.timeout_states)
        if (session.session_state not in ACTIVE_SESSION_STATES
                or len(self.doc.timeout_states) == 1):
            return

        # 6: Else, clone the current task with the next timeout state
        # await Task(await TaskItemModel(
        #    target=self.doc.target,
        #    task_type=self.doc.task_type,
        #    assigned_station=self.doc.assigned_station,
        #    assigned_session=session,
        #    assigned_locker=self.doc.assigned_locker,
        #    timeout_states=self.doc.timeout_states[1:],
        #    moves_session=self.doc.moves_session,
        # ).insert()).evaluate_queue_state()

        # 7: Restart the expiration manager
        # task_expiration_manager.restart()


async def expiration_manager_loop() -> None:
    """Coordinate the expiration of tasks.
    Get the time to the next expiration, then wait until the task expires.
    If the task is still pending, fire up the expiration handler.

    Raises:
        AssertionError: If the task has already expired or has no expiration date
    """
    # 1: Get time to next expiration
    next_expiring_task: TaskItemModel = await TaskItemModel.find(
        TaskItemModel.task_state == TaskState.PENDING
    ).sort(
        (TaskItemModel.expires_at, SortDirection.ASCENDING)
    ).first_or_none()
    if next_expiring_task is None:
        return

    sleep_duration: int = (
        next_expiring_task.expires_at - datetime.now()).total_seconds()
    assert (sleep_duration > 0
            ), f"Task '{next_expiring_task.id}' has already expired."
    logger.debug(f"Task '#{next_expiring_task.id}' will expire next in {
                 sleep_duration} seconds")

    # 2: Wait until the task expired
    await sleep(sleep_duration)

    # 3: Check if the task is still pending, then fire up the expiration handler
    await next_expiring_task.sync()  # TODO: Is this required here?
    if next_expiring_task.task_state == TaskState.PENDING:
        await Task(next_expiring_task).handle_expiration()


class TaskExpirationManager:
    """Task expiration manager."""

    def __init__(self) -> None:
        self.task: Optional[Task] = None

    def restart(self) -> None:
        """Restart the task expiration manager."""
        if self.task:
            self.task.cancel()
        self.task = create_task(expiration_manager_loop())


task_expiration_manager = TaskExpirationManager()
