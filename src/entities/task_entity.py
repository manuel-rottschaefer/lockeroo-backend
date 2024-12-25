"""This module provides utilities for  database for tasks."""

# Basics
from typing import Optional
from datetime import datetime, timedelta
from asyncio import sleep, create_task
import os

# Beanie
from beanie import SortDirection, Link
from beanie.operators import In

# Entities
from src.entities.entity_utils import Entity
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker
from src.models.session_models import (
    SessionModel, SessionState,
    FOLLOW_UP_STATES,
    SESSION_TIMEOUTS,
    ACTIVE_SESSION_STATES)
# Models
from src.models.station_models import TerminalState
from src.models.locker_models import LockerState
from src.models.station_models import StationModel
from src.models.task_models import TaskItemModel, TaskState, TaskType, TaskTarget
# Services
from src.services.mqtt_services import fast_mqtt
from src.services.logging_services import logger


class Task(Entity):
    """Add behaviour to a task Model."""
    doc: TaskItemModel

    @property
    def exists(self) -> bool:
        return self.doc is not None

    @classmethod
    async def get_next_in_queue(cls, station_id: str) -> Optional['Task']:
        """Get the next task in queue at the station of the current task."""
        task_item = await TaskItemModel.find(
            TaskItemModel.assigned_station.id == station_id,  # pylint: disable=no-member
            TaskItemModel.target == TaskTarget.TERMINAL,
            In(TaskItemModel.task_state, [
               TaskState.PENDING, TaskState.QUEUED]),
            fetch_links=True
        ).sort(
            (TaskItemModel.created_at, SortDirection.ASCENDING)
        ).first_or_none()

        if task_item:
            return cls(task_item)

    async def is_next_in_queue(self) -> bool:
        """Get the next task in queue at a station and check if this task is next in queue."""
        # 1: Check if the station is still occupied
        await self.doc.fetch_link(TaskItemModel.assigned_station)
        await self.assigned_station.sync()  # TODO: Is this required here?
        if (self.assigned_station.terminal_state != TerminalState.IDLE
                and self.doc.task_type != TaskType.REPORT):
            logger.info(
                f"Not proceeding with queue activation, Station "
                f"'{self.assigned_station.callsign}' is still occupied.")
            return False

        # 2: Find the next task in queue or pending task
        next_task: Task = await Task.get_next_in_queue(
            station_id=self.doc.assigned_station.id)

        # If the next task is pending, return None
        if next_task is not None and next_task.id == self.id:
            # logger.debug((f"Task '#{next_task.id}' identified "
            #              f"as next in queue at station '#{self.id}'."))
            return True
        elif next_task.doc.task_state == TaskState.PENDING:
            logger.info(
                f"Not proceeding with queue activation, "
                f"Task '#{next_task.id}' is still pending."
            )

    async def move_in_queue(self):
        """Evaluate the position of this task in the queue and activate it in case it is next."""
        await self.doc.fetch_link(TaskItemModel.assigned_station)
        station = self.doc.assigned_station

        # Tasks that are not terminal tasks are activated immediately
        if self.target != TaskTarget.TERMINAL:
            await self.activate()

        elif self.doc.task_type == TaskType.REPORT:
            if await self.is_next_in_queue():
                await self.activate()

        # Do not activate a task if the terminal is still occupied.
        elif station.terminal_state != TerminalState.IDLE:
            return

        # Report tasks for terminals are activated immediately
        # elif self.doc.task_type == TaskType.REPORT:
        elif await self.is_next_in_queue():
            await self.activate()

    ### Session runner ###

    def get_timeout_window(self) -> int:
        """Get the timeout window in seconds depending on the task context"""
        timeout_window = 0
        if self.doc.target in [TaskTarget.USER, TaskTarget.LOCKER]:
            timeout_window = SESSION_TIMEOUTS[
                self.doc.assigned_session.session_state]

        elif self.target == TaskTarget.TERMINAL:
            timeout_window = int(os.getenv("STATION_EXPIRATION", '10'))

        assert (timeout_window is not None
                ), f"No timeout window found for task '#{self.doc.id}'."

        return timeout_window

    async def instruct_terminal_state(self, session_state: SessionState) -> None:
        """Apply a session state to the terminal"""
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
        assert (self.doc.task_state == TaskState.QUEUED
                ), f"Task '#{self.doc.id}' is not queued."

        # 1: Get the assigned session
        session: Session = Session(self.doc.assigned_session)

        # 2: Get the timeout window for terminal confirmation
        timeout_window = self.get_timeout_window()
        timeout_date: datetime = self.doc.created_at + \
            timedelta(seconds=timeout_window)

        # 3: Update task item
        self.doc.task_state = TaskState.PENDING
        self.doc.activated_at = datetime.now()
        self.doc.expires_at = timeout_date
        self.doc.expiration_window = timeout_window
        await self.doc.save_changes()

        # logger.debug(
        #    (f"Task '#{self.doc.id}' will time out to "
        #     f"{self.doc.timeout_states[0]} in {timeout_window} seconds."))

        # If the task awaits a user report, advance the session state
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
        await restart_expiration_manager()

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
        await self.doc.sync()
        assert (self.doc.task_state == TaskState.PENDING
                ), f"Cannot complete Task '#{self.doc.id}' as it is in {self.doc.task_state}."

        assert (datetime.now() < self.doc.expires_at
                ), f"Cannot complete Task '#{self.doc.id}' as it should already have timed out."

        # 1: Set the task state to completed
        self.doc.task_state = TaskState.COMPLETED
        self.doc.completed_at = datetime.now()
        await self.doc.save_changes()

        await self.doc.fetch_link(TaskItemModel.assigned_station)
        await self.doc.assigned_station.sync()

        # 2: If this was a terminal task, enable the next task in queue
        is_terminal_idle: bool = self.doc.assigned_station.terminal_state == TerminalState.IDLE
        if (self.doc.target == TaskTarget.TERMINAL
                and self.doc.task_type == TaskType.REPORT and is_terminal_idle):
            next_task: Task = await Task.get_next_in_queue(
                station_id=self.doc.assigned_station.id)
            if next_task.exists:
                logger.debug(
                    f"Task completed, Task '#{next_task.id}' is next at station.")
                await next_task.activate()

    async def handle_expiration(self) -> None:
        """Handle the expiration of a task item."""
        # 1: Refresh task document
        await self.doc.sync()

        # 2: If task is still pending, set it to expired
        assert (self.doc.task_state == TaskState.PENDING
                ), f"Task '#{self.id}' is not pending."
        self.doc.task_state = TaskState.EXPIRED

        # 2: Update the session state to its timeout state
        await self.doc.fetch_link(TaskItemModel.assigned_session)
        session: SessionModel = self.doc.assigned_session
        assert len(self.timeout_states
                   ), f"No timeout states defined for task '#{self.id}'."
        self.doc.assigned_session.session_state = self.timeout_states[0]

        # 3: Save changes
        await self.doc.save_changes()
        await session.save_changes()

        # 4: Restart the expiration manager
        await restart_expiration_manager()

        # 5: End the queue flow here if the session has timed out or no additional timeout states
        if (session.session_state not in ACTIVE_SESSION_STATES
                or len(self.timeout_states) == 1):
            return

        # 7: Else, clone the current task with the next timeout state
        await Task(await TaskItemModel(
            target=self.doc.target,
            task_type=self.doc.task_type,
            assigned_station=self.doc.assigned_station,
            assigned_session=self.doc.assigned_session,
            assigned_locker=self.doc.assigned_locker,
            timeout_states=self.doc.timeout_states[1:],
            moves_session=self.doc.moves_session,
        ).insert()).move_in_queue()


async def expiration_manager_loop() -> None:
    """Handle expirations."""
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

    # 2: Wait until the task expired
    await sleep(sleep_duration)

    # 3: Check if the task is still pending, then fire up the expiration handler
    await next_expiring_task.sync()  # TODO: Is this required here?
    if next_expiring_task.task_state == TaskState.PENDING:
        await Task(next_expiring_task).handle_expiration()


async def restart_expiration_manager() -> None:
    """Restart the expiration manager."""
    EXPIRATION_MANAGER.cancel()
    await start_expiration_manager()


async def start_expiration_manager() -> None:
    """Start the expiration manager."""
    global EXPIRATION_MANAGER  # pylint: disable=global-statement
    EXPIRATION_MANAGER = create_task(expiration_manager_loop())


EXPIRATION_MANAGER = None
