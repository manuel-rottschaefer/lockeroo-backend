"""This module provides utilities for  database for tasks."""
# Basics
from asyncio import Task as AsyncTask, create_task, sleep, Lock
from datetime import datetime, timedelta
from configparser import ConfigParser
from typing import Optional
# Beanie
from beanie import Link, SortDirection
from beanie.operators import In
# Entities
from src.entities.entity_utils import Entity
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.models.locker_models import LockerState
from src.models.session_models import (
    ACTIVE_SESSION_STATES,
    SESSION_TIMEOUTS,
    SessionState)
# Models
from src.models.station_models import TerminalState
from src.models.task_models import (
    TaskItemModel,
    TaskState,
    TaskTarget,
    TaskType)
# Services
from src.services.logging_services import logger_service as logger

base_config = ConfigParser()
base_config.read('.env')


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
        assert self.doc.target is not None, (
            f"No target found for task '"
            f"#{self.doc.id}'.")

        timeout_window: int = 0
        if self.doc.task_type == TaskType.CONFIRMATION:
            timeout_window = int(base_config.get(
                'TARGET_EXPIRATIONS', 'STATION'))
        elif self.doc.task_type == TaskType.RESERVATION:
            timeout_window = int(base_config.get(
                'TARGET_EXPIRATIONS', 'RESERVATION'))
        else:
            timeout_window = SESSION_TIMEOUTS.get(
                self.doc.assigned_session.session_state, 10)

        assert (timeout_window is not None
                ), (f"No timeout window found for task '#{self.doc.id}' "
                    f"in {self.doc.assigned_session.session_state}.")
        return timeout_window

    ### Class methods ###
    async def evaluate_next(self):
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
            TaskItemModel.assigned_station.id == self.doc.assigned_station.id,  # pylint: disable=no-member
            TaskItemModel.target == TaskTarget.TERMINAL,
            TaskItemModel.task_state == TaskState.PENDING,
            fetch_links=True
        ).count() > 0:
            task_expiration_manager.restart()
            return Task()

        # 2: Get the next task in queue
        next_task = Task(await TaskItemModel.find(
            TaskItemModel.assigned_station.id == self.doc.assigned_station.id,  # pylint: disable=no-member
            TaskItemModel.target == TaskTarget.TERMINAL,
            TaskItemModel.task_state == TaskState.QUEUED,
            fetch_links=True
        ).sort(
            (TaskItemModel.created_at, SortDirection.ASCENDING)
        ).first_or_none())
        if next_task.exists:
            #  TODO: Verify that lock is required and useful in preventing duplicate task launches
            async with Lock():
                await next_task.evaluate_queue_state()
        else:
            task_expiration_manager.restart()

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
        # 1: Get the complete queue at the station
        await self.doc.fetch_link(TaskItemModel.assigned_station)
        tasks = await TaskItemModel.find(
            TaskItemModel.assigned_station.id == self.doc.assigned_station.id,  # pylint: disable=no-member
            In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
               ACTIVE_SESSION_STATES),
            TaskItemModel.target == TaskTarget.TERMINAL,
            In(TaskItemModel.task_state, [
               TaskState.QUEUED, TaskState.PENDING]),
            fetch_links=True
        ).sort(
            (TaskItemModel.created_at, SortDirection.ASCENDING)
        ).to_list()
        # If there are no tasks or a task is pending, quit
        if (len(tasks) == 0 or any(
                task.task_state == TaskState.PENDING for task in tasks)):
            return 0

        # 2: Decrease queue position for each task
        for pos, task in enumerate(tasks):
            task.queue_position = pos
            await task.save_changes()

        # 3: Start the next task in the queue

        first_task = Task(tasks[0])
        if first_task.doc.id != self.doc.id:
            logger.info((f"Task '#{self.doc.id}' is not next, but '"
                         f"#{first_task.doc.id}'."))
        assert (first_task.assigned_session is not None
                ), f"Task '#{first_task.id}' has no assigned session."

        front_task = None
        for task in tasks:
            next_task = Task(task)
            await next_task.doc.fetch_all_links()

            # Do not start a task with a session that is not active
            if next_task.doc.assigned_session.session_state not in ACTIVE_SESSION_STATES:
                logger.debug((
                    f"Not activating task '#{next_task.id} '"
                    "as session is not active."))
                continue

            # Dont activate a terminal task if the terminal is not idle
            if (next_task.doc.target == TaskTarget.TERMINAL and
                    next_task.doc.assigned_station.terminal_state != TerminalState.IDLE):
                logger.debug((
                    f"Not activating task '#{next_task.id}' "
                    "as terminal is not idle."))
                continue

            front_task = next_task
            break

        if front_task is None:
            logger.debug((
                f"No task found to activate at station '"
                f"{self.doc.assigned_station.callsign}'."))
            return -1

        # 4: Activate the next task
        if front_task.doc.queued_state is None:
            session = Session(front_task.doc.assigned_session)
            await session.broadcast_update(front_task)

        assert front_task.doc.task_state == TaskState.QUEUED, (
            f"Task '#{front_task.doc.id}' is in '{front_task.doc.task_state}'.")
        await front_task.activate()

        # TODO: Check if required
        task_expiration_manager.restart()

        # Return queue position of current task
        return self.doc.queue_position

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
        await self.doc.sync()
        if self.doc.task_state != TaskState.QUEUED:
            logger.warning(
                f"Task '#{self.doc.id}' is not queued, but {self.doc.task_state}.")
            return
        assert (self.doc.task_state == TaskState.QUEUED
                ), f"Task '#{self.doc.id}' is not queued."

        session: Session = (
            Session(self.doc.assigned_session)
            if self.doc.task_type != TaskType.RESERVATION else None)

        # 2: Execute specific actions based on the task type
        if session:
            await session.activate(self.doc)

        # 3: Common activation steps
        timeout_window = self.timeout_window
        timeout_date = datetime.now() + timedelta(seconds=timeout_window)
        self.doc.task_state = TaskState.PENDING
        self.doc.activated_at = datetime.now()
        self.doc.expires_at = timeout_date
        self.doc.expiration_window = timeout_window
        await self.doc.save_changes()
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

        # 3: Reset the session timeout counter
        if self.doc.target == TaskTarget.TERMINAL and self.doc.task_type == TaskType.REPORT:
            self.doc.assigned_session.timeout_count = 0
            await self.doc.assigned_session.save_changes()

        # 4: If the stations terminal is not idle, end here
        await self.doc.fetch_link(TaskItemModel.assigned_station)
        # await self.doc.assigned_station.sync()
        if self.doc.assigned_station.terminal_state != TerminalState.IDLE:
            return

        # 5: Else, start the next task
        # This is to avoid redundant task activations due to concurrency
        # TODO: Find a better solution for concurrency problems
        if self.doc.target == TaskTarget.TERMINAL:
            return self.evaluate_next()

        # 6: Save session state and restart the expiration manager
        task_expiration_manager.restart()

    async def cancel(self) -> None:
        """Cancel a task item.
        Checks if the task is still queued or pending, then updates it to CANCELED.
        If the task is a terminal task, sends an instruction to the terminal to be idle.
        Finally, restarts the expiration manager.

        Args:
            self (Task): The own task entity

        Returns:
            None

        Raises:
            AssertionError: If the task is not pending
        """
        # 1: Sync the task and check if its still pending
        await self.doc.sync()
        assert (self.doc.task_state in [TaskState.QUEUED, TaskState.PENDING]
                ), f"Task '#{self.id}' is not pending."
        self.doc.task_state = TaskState.CANCELED

        # 2: Update the task item
        await self.doc.save_changes()

        # 3: If the task targeted a terminal, send an instruction for it to be idle
        if self.doc.target == TaskTarget.TERMINAL:
            await self.doc.fetch_all_links()
            if self.doc.assigned_station.terminal_state != TerminalState.IDLE:
                await Task(await TaskItemModel(
                    target=TaskTarget.TERMINAL,
                    task_type=TaskType.CONFIRMATION,
                    assigned_user=self.doc.assigned_user,
                    assigned_session=self.doc.assigned_session,
                    assigned_station=self.doc.assigned_station,
                    queued_state=SessionState.CANCELED,
                    timeout_states=[SessionState.ABORTED],
                ).insert()).activate()

        # If the task targeted an open locker, send an instruction for it to be locked
        elif self.doc.target == TaskTarget.LOCKER:
            await self.doc.fetch_all_links()
            if self.doc.assigned_locker.locker_state == LockerState.UNLOCKED:
                await Task(await TaskItemModel(
                    target=TaskTarget.LOCKER,
                    task_type=TaskType.REPORT,
                    assigned_user=self.doc.assigned_user,
                    assigned_session=self.doc.assigned_session,
                    assigned_station=self.doc.assigned_station,
                    assigned_locker=self.doc.assigned_locker,
                    timeout_states=[SessionState.STALE],
                ).insert()).activate()
                task_expiration_manager.restart()

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
        print(f"Handling expiration of task '{self.doc.id}'")
        # 1: Sync the task and check if its still pending
        await self.doc.sync()
        # 2: If task is still pending, set it to expired
        assert (self.doc.task_state == TaskState.PENDING
                ), f"Task '#{self.id}' is not pending."
        self.doc.task_state = TaskState.EXPIRED

        assert len(self.doc.timeout_states
                   ), f"No timeout states defined for task '#{self.doc.id}'."

        await self.doc.save_changes()

        # 3: Update the session state to its timeout state
        await self.doc.fetch_all_links()
        session = Session(self.doc.assigned_session)
        station = Station(self.doc.assigned_station)

        # 5: If the session is stale, mark the locker as stale too
        if session.doc.session_state == SessionState.STALE:
            # await self.doc.fetch_link(TaskItemModel.assigned_locker)
            await self.doc.assigned_locker.register_state(LockerState.STALE)
            # For a stale session, there should be no additional timeout states
            assert len(self.doc.timeout_states) == 1, (
                f"Stale session '#{session.id}' has additional registered timeout states.")

        # 8: Save the session changes and restart the expiration manager
        session.doc.timeout_count += 1
        await session.doc.save_changes()

        # 6: If the task targeted a terminal, send an instruction for it to be idle
        # TODO: Rework this logic
        task_activated: bool = False
        if (self.doc.target == TaskTarget.TERMINAL and
            self.doc.task_type == TaskType.REPORT and
                self.doc.timeout_states[0] != SessionState.EXPIRED):
            await Task(await TaskItemModel(
                target=TaskTarget.TERMINAL,
                task_type=TaskType.CONFIRMATION,
                assigned_user=self.doc.assigned_user,
                assigned_station=station.doc,
                assigned_session=session.doc,
                timeout_states=[SessionState.ABORTED],
                queued_state=self.doc.timeout_states[0],
                is_expiration_retry=True
            ).insert()).activate()
            task_activated = True
            station: Station = Station(self.doc.assigned_station)
            await station.instruct_next_terminal_state(SessionState.EXPIRED)
        else:
            session.set_state(self.doc.timeout_states[0])
            await session.doc.save_changes()
            await session.broadcast_update()

        # If the session is still in an active state, await the next user action
        if session.doc.session_state in ACTIVE_SESSION_STATES:
            await Task(await TaskItemModel(
                target=TaskTarget.USER,
                task_type=TaskType.REPORT,
                assigned_user=self.doc.assigned_user,
                assigned_station=station.doc,
                assigned_session=session.doc,
                timeout_states=self.doc.timeout_states[1:],
            ).insert()).activate()
            task_activated = True

        # 7: If no task was activated, evaluate the next task
        if not task_activated or len(self.doc.timeout_states) == 1:
            await self.evaluate_next()

        task_expiration_manager.restart()


async def expiration_manager_loop() -> None:
    """Coordinate the expiration of tasks.
    Get the time to the next expiration, then wait until the task expires.
    If the task is still pending, fire up the expiration handler.

    Raises:
        AssertionError: If the task has already expired or has no expiration date
    """
    # 1: Get time to next expiration
    next_expiring_task: TaskItemModel = await TaskItemModel.find(
        TaskItemModel.task_state == TaskState.PENDING,
    ).sort(
        (TaskItemModel.expires_at, SortDirection.ASCENDING)
    ).first_or_none()
    if next_expiring_task is None:
        return
    assert (next_expiring_task.expires_at is not None
            ), f"No expiration date found for task '#{next_expiring_task.id}'."

    sleep_duration: int = (
        next_expiring_task.expires_at - datetime.now()).total_seconds()

    # 2: Wait until the task expired
    if sleep_duration > 0:
        logger.debug((
            f"Task '#{next_expiring_task.id}' will expire next "
            f"to {next_expiring_task.timeout_states[0]} "
            f"in {round(sleep_duration)} seconds."))
    else:
        logger.debug((
            f"Task '#{next_expiring_task.id}' should have expired "
            f"{round(sleep_duration)} seconds ago."))

    # 3: Check if the task is still pending, then fire up the expiration handler
    await sleep(sleep_duration)
    await next_expiring_task.sync()
    if next_expiring_task.task_state == TaskState.PENDING:
        await Task(next_expiring_task).handle_expiration()


class TaskExpirationManager:
    """Task expiration manager."""

    def __init__(self) -> None:
        self.task: Optional[AsyncTask] = None

    def restart(self) -> None:
        """Restart the task expiration manager."""
        if self.task:
            self.task.cancel()
        self.task = create_task(expiration_manager_loop())


task_expiration_manager = TaskExpirationManager()
