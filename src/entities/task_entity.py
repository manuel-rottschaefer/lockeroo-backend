"""
Lockeroo.task_entity
-------------------------
This module provides the Task Entity class

Key Features:
    - Provides a functionality wrapper for Beanie Documents

Dependencies:
    - beanie
"""
# Basics
from asyncio import Lock
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
# Beanie
from beanie import SortDirection, Link
# Entities
from src.entities.entity import Entity
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.locker_entity import Locker
from src.entities.snapshot_entity import Snapshot
# Models
from lockeroo_models.locker_models import (
    LockerState)
from lockeroo_models.session_models import (
    ACTIVE_SESSION_STATES,
    SessionState)
from lockeroo_models.station_models import TerminalState
from lockeroo_models.snapshot_models import SnapshotModel
from lockeroo_models.task_models import (
    TaskItemModel,
    TaskState,
    TaskTarget,
    TaskType)
# Services
from src.services.config_services import cfg
from src.services.logging_services import logger_service as logger


SESSION_TIMEOUTS: Dict[SessionState, int] = {
    SessionState.CREATED: float(
        cfg.get("SESSION_EXPIRATIONS", 'CREATED', fallback='0')),
    SessionState.PAYMENT_SELECTED: float(
        cfg.get("SESSION_EXPIRATIONS", 'PAYMENT_SELECTED', fallback='0')),
    SessionState.VERIFICATION: float(
        cfg.get("SESSION_EXPIRATIONS", 'VERIFICATION', fallback='0')),
    SessionState.STASHING: float(
        cfg.get("SESSION_EXPIRATIONS", 'STASHING', fallback='0')),
    SessionState.ACTIVE: float(
        cfg.get("SESSION_EXPIRATIONS", 'ACTIVE', fallback='0')),
    SessionState.HOLD: float(
        cfg.get("SESSION_EXPIRATIONS", 'HOLD', fallback='0')),
    SessionState.PAYMENT: float(
        cfg.get("SESSION_EXPIRATIONS", 'PAYMENT', fallback='0')),
    SessionState.RETRIEVAL: float(
        cfg.get("SESSION_EXPIRATIONS", 'RETRIEVAL', fallback='0')),
    SessionState.COMPLETED: float(
        cfg.get("SESSION_EXPIRATIONS", 'COMPLETED', fallback='0')),
    SessionState.CANCELED: float(
        cfg.get("SESSION_EXPIRATIONS", 'CANCELED', fallback='0')),
    SessionState.STALE: float(
        cfg.get("SESSION_EXPIRATIONS", 'STALE', fallback='0')),
    SessionState.EXPIRED: float(
        cfg.get("SESSION_EXPIRATIONS", 'EXPIRED', fallback='0')),
    SessionState.ABORTED: float(
        cfg.get("SESSION_EXPIRATIONS", 'ABORTED', fallback='0')),
}


class Task(Entity):
    """
    Lockeroo.Task
    -------
    A class representing a task. A task is an action or response by a user or station that is
    awaited by the backend. Tasks are created to keep track of the running sessions without creating
    a seperate thread for each session.

    Key Features:
    - `__init__`: Initializes a task object and adds event logic to it
    - 'timeout_window': Returns the timeout window of the given task
    - 'find_next': Returns the next task in the global queue
    - 'evaluate_queue_state': Returns the position of a task in the station queue
    - 'handle_expiration': Evaluation logic for expired tasks
    - 'activate': Activates a task
    - 'complete': Completes a task
    - 'cancel': Canceles a task
    """
    doc: TaskItemModel

    def __init__(self, document=None):
        super().__init__(document)
        self._add_handlers()

    def _add_handlers(self):
        async def handle_task_creation_logic(task: TaskItemModel):
            """Task Creation Handler"""
            await task.fetch_link(TaskItemModel.assigned_session)
            if task.assigned_session is not None:
                logger.debug(
                    (f"Created task '#{task.id}' of {task.task_type} "
                     f"at station '#{task.assigned_station.callsign}'."),
                    session_id=task.assigned_session.id)  # pylint: disable=no-member

        async def handle_task_logging(task: TaskItemModel):
            """Log database operation."""
            # await task.fetch_link(TaskItemModel.assigned_session)

            if task.task_state != TaskState.QUEUED:
                logger.debug((
                    f"Task '#{task.id}' for {task.target} of "
                    f"{task.task_type} set to {task.task_state}."))
                #  session_id=session_id)  # pylint: disable=no-member

        TaskItemModel.log_state = handle_task_logging
        TaskItemModel.log_creation = handle_task_creation_logic

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
            timeout_window = int(cfg.get(
                'TARGET_EXPIRATIONS', 'STATION'))
        elif self.doc.task_type == TaskType.RESERVATION:
            timeout_window = int(cfg.get(
                'TARGET_EXPIRATIONS', 'RESERVATION'))
        else:
            if cfg.get("MOCKING", "MOCK_MODE") == "DEFAULT":
                timeout_window = SESSION_TIMEOUTS.get(
                    self.doc.assigned_session.session_state, 0)
            else:
                timeout_window = int(cfg.get("MOCKING", "MOCK_EXPIRATION"))

        assert (timeout_window is not None
                ), (f"No timeout window found for task '#{self.doc.id}' "
                    f"in {self.doc.assigned_session.session_state}.")
        return timeout_window

    async def get_queue_position(self):
        # Get all tasks with target terminal and state queued at this station
        task_amount = await TaskItemModel.find(
            TaskItemModel.target == TaskTarget.TERMINAL,
            TaskItemModel.assigned_station.id == self.doc.assigned_station.id,  # pylint: disable=no-member
            TaskItemModel.task_state == TaskState.QUEUED,
            TaskItemModel.task_type != TaskType.RESERVATION,
            fetch_links=True
        ).count()
        self.doc.queue_position = task_amount + 1
        await self.doc.save_changes(skip_actions=['_log_state'])
        return self.doc.queue_position

    async def evaluate_queue(self, task_manager):
        """Combines all other queue evaluation methods."""
        await self.doc.fetch_all_links()
        # Activate all tasks which are not targeting a terminal and are still queued
        async for task in TaskItemModel.find(
            TaskItemModel.target != TaskTarget.TERMINAL,
            TaskItemModel.task_state == TaskState.QUEUED,  # pylint: disable=no-member
        ).sort((TaskItemModel.created_at, SortDirection.ASCENDING)):
            task = Task(task)
            await task.activate(task_manager=task_manager)

        # Check if there is still a pending terminal task
        if await TaskItemModel.find(
            TaskItemModel.target == TaskTarget.TERMINAL,
            TaskItemModel.task_state == TaskState.PENDING,
            TaskItemModel.task_type != TaskType.RESERVATION,
            TaskItemModel.assigned_station.id == self.doc.assigned_station.id,  # pylint: disable=no-member
        ).count() > 0:
            logger.debug(
                "Terminal task is still pending, skipping queue evaluation.", session_id=self.doc.assigned_session.id)  # pylint: disable=no-member
            # ToDo: Verify this
            task_manager.restart()
            return

        # Evaluate terminal tasks
        queued_tasks = await TaskItemModel.find(
            TaskItemModel.target == TaskTarget.TERMINAL,
            TaskItemModel.task_state == TaskState.QUEUED,
            TaskItemModel.task_type != TaskType.RESERVATION,
            TaskItemModel.assigned_station.id == self.doc.assigned_station.id,  # pylint: disable=no-member
        ).sort((TaskItemModel.created_at, SortDirection.ASCENDING)).to_list()

        if not len(queued_tasks):
            return

        first_task = Task(queued_tasks[0])
        await first_task.doc.fetch_all_links()

        async with Lock():  # TODO: Verify this
            terminal_state = first_task.doc.assigned_station.terminal_state
            if (first_task.doc.target == TaskTarget.TERMINAL and
                first_task.doc.queued_state != TerminalState.IDLE and
                    terminal_state != TerminalState.IDLE):
                logger.debug((
                    f"Not activating task '#{first_task.id}' as terminal at "
                    f"'#{first_task.doc.assigned_station.callsign}' is not idle."))
                return
            await first_task.activate(task_manager=task_manager)

        # Calculate queue position of all tasks
        for pos, task in enumerate(queued_tasks[1:], start=1):
            if task.queue_position != pos:
                task.queue_position = pos
                await task.save_changes()
                logger.debug(
                    f"Task '#{task.id}' is queued at station with position {task.queue_position}",
                    session_id=self.doc.assigned_session.id)  # pylint: disable=no-member

        # if first_task.doc.assigned_session.session_state not in ACTIVE_SESSION_STATES:
        #    logger.debug((
        #        f"Not activating task '#{first_task.id} '"
        #        "as session is not active."))
        #    return

        # terminal_state = first_task.doc.assigned_station.terminal_state
        # if (first_task.doc.target == TaskTarget.TERMINAL and
        #    first_task.doc.queued_state != TerminalState.IDLE and
        #        terminal_state != TerminalState.IDLE):
        #    logger.debug((
        #        f"Not activating task '#{first_task.id}' as terminal at "
        #        f"'#{first_task.doc.assigned_station.callsign}' is not idle."))
        #    return

    async def handle_expiration(self, task_manager):
        """Handle the expiration of a task item.
        Checks if the task is still pending, then sets it to expired and updates the session state
        to the next timeout state in the task\'s timeout states list.
        Finally, restarts the expiration manager.

        Args:
            self (Task): The own task entity

        Returns:
            None

        Raises:
            AssertionError: If the task is not pending or has no timeout states defined
        """
        logger.debug(f"Handling expiration for task #{self.doc.id}...")
        await self.doc.fetch_all_links()  # Fetch links for the current task document

        # 1. Handle tasks without a session (e.g., reservations) or if session cannot be fetched
        if isinstance(self.doc.assigned_session, Link) is False and self.doc.assigned_session is None:
            logger.debug(
                f"Task \'#{self.doc.id}\' has no assigned session (e.g. reservation). Marking as EXPIRED.")
            if self.doc.task_state == TaskState.PENDING:
                self.doc.task_state = TaskState.EXPIRED
                await self.doc.save_changes()
            return

        session_doc = await self.doc.assigned_session.fetch() if isinstance(self.doc.assigned_session, Link) else self.doc.assigned_session
        if not session_doc:
            logger.error(
                f"Task \'#{self.doc.id}\' has an assigned session reference, but the session document could not be fetched. Marking task EXPIRED.")
            if self.doc.task_state == TaskState.PENDING:
                self.doc.task_state = TaskState.EXPIRED
                await self.doc.save_changes()
            return

        session: Session = Session(session_doc)

        # 2. Set current task to EXPIRED and update session timeout count
        self.doc.task_state = TaskState.EXPIRED
        logger.debug(f"Task {self.doc.id} set to expired.")
        await self.doc.save_changes()
        session.doc.timeout_count += 1

        # Safely fetch linked locker and station documents from the session document
        locker_doc = None
        if session.doc.assigned_locker:  # Check if the attribute exists and is not None
            locker_doc = await session.doc.assigned_locker.fetch() if isinstance(session.doc.assigned_locker, Link) else session.doc.assigned_locker

        station_doc = None
        if session.doc.assigned_station:  # Check if the attribute exists and is not None
            station_doc = await session.doc.assigned_station.fetch() if isinstance(session.doc.assigned_station, Link) else session.doc.assigned_station

        locker: Optional[Locker] = Locker(locker_doc) if locker_doc else None
        station: Optional[Station] = Station(
            station_doc) if station_doc else None

        if not station or not station.exists:  # Station is crucial for most session operations
            logger.error(
                f"Task \'#{self.doc.id}\' for session \'#{session.doc.id}\' is missing essential station information. Marking task EXPIRED.")
            if self.doc.task_state == TaskState.PENDING:
                self.doc.task_state = TaskState.EXPIRED
                await self.doc.save_changes()
            return

        # 3. Determine next session state based on task's timeout_states
        # Default if no specific state defined
        next_session_timeout_state = SessionState.ABORTED
        if self.doc.timeout_states:
            next_session_timeout_state = self.doc.timeout_states[0]
        else:
            logger.warning(
                f"Task \'#{self.doc.id}\' for session \'#{session.doc.id}\' has no timeout_states defined. Defaulting next session state to {next_session_timeout_state}.")

        # 4. Update session state, considering locker state
        if locker and locker.exists and locker.doc.locker_state == LockerState.UNLOCKED:
            logger.info(
                f"Session \'#{session.doc.id}\' (task \'#{self.doc.id}\'): Locker \'#{locker.doc.id}\' is UNLOCKED. Setting session to STALE.")
            session.set_state(SessionState.STALE)
            # This also saves the locker
            await locker.register_state(LockerState.STALE)
            if not self.doc.timeout_states:
                logger.warning(
                    f"Task \'#{self.doc.id}\' led to STALE session \'#{session.doc.id}\', and the task had no timeout_states defined.")
        else:
            if locker and locker.exists:
                logger.info(
                    f"Session \'#{session.doc.id}\' (task \'#{self.doc.id}\'): Locker \'#{locker.doc.id}\' state is \'{locker.doc.locker_state}\'. Setting session to {next_session_timeout_state}.")
            else:
                logger.info(
                    f"Session \'#{session.doc.id}\' (task \'#{self.doc.id}\'): No locker information or locker does not exist. Setting session to {next_session_timeout_state}.")
            session.set_state(next_session_timeout_state)

        await session.doc.save_changes()  # Save session state changes

        # 5. Stop other PENDING tasks for this session
        async for other_task_doc in TaskItemModel.find(
            TaskItemModel.assigned_session.id == session.doc.id,
            TaskItemModel.task_state == TaskState.PENDING,
            TaskItemModel.id != self.doc.id  # Don't try to expire itself again
        ):
            logger.info(
                f"Expiring other PENDING task \'#{other_task_doc.id}\' for session \'#{session.doc.id}\'.")
            other_task_doc.task_state = TaskState.EXPIRED
            await other_task_doc.save_changes()

        # 6. Save current task's changes (already set to EXPIRED)
        await self.doc.save_changes()

        # 7. Create a snapshot of the session state
        await Snapshot(SnapshotModel(
            assigned_session=session.doc,  # Pass the fetched document
            session_state=session.doc.session_state,
        )).insert()

        # 8. Handle creation of subsequent tasks
        # For Terminal Report tasks that expired:
        if (self.doc.target == TaskTarget.TERMINAL and
                self.doc.task_type == TaskType.REPORT):
            logger.info(
                f"Task \'#{self.doc.id}\' (session \'#{session.doc.id}\') awaited terminal report, now creating CONFIRMATION task for terminal IDLE.",
                session_id=session.doc.id)
            await Task(TaskItemModel(
                target=TaskTarget.TERMINAL,
                task_type=TaskType.CONFIRMATION,
                # Assuming this is a direct ID or a resolvable ref
                assigned_user=self.doc.assigned_user,
                assigned_station=station.doc,  # Pass the fetched document
                assigned_session=session.doc,  # Pass the fetched document
                # Fixed timeout for this new task
                timeout_states=[SessionState.ABORTED],
                queued_state=TerminalState.IDLE,
                is_expiration_retry=False
            )).insert()

        # For User Report tasks that expired (if session is still active):
        next_user_task_timeout_states = []
        if len(self.doc.timeout_states) > 1:
            next_user_task_timeout_states = self.doc.timeout_states[1:]
        elif self.doc.timeout_states:  # Had one state, so [1:] is empty
            logger.info(
                f"Task \'#{self.doc.id}\' (session \'#{session.doc.id}\') had one timeout state. Next user task will have no further timeout states.")
        else:  # Had no states originally
            logger.warning(
                f"Task \'#{self.doc.id}\' (session \'#{session.doc.id}\') had no timeout states. Next user task will also have no further timeout states.")

        if session.doc.session_state in ACTIVE_SESSION_STATES:
            logger.info(
                f"Task \'#{self.doc.id}\' (session \'#{session.doc.id}\') awaited user action, session is {session.doc.session_state}. Launching next chance with timeout states: {next_user_task_timeout_states}.",
                session_id=session.doc.id)
            await Task(TaskItemModel(
                target=TaskTarget.USER,
                task_type=TaskType.REPORT,
                assigned_user=self.doc.assigned_user,
                assigned_station=station.doc,
                assigned_session=session.doc,
                timeout_states=next_user_task_timeout_states,
            )).insert()

        # 9. Evaluate station queue for any newly created or pending tasks
        # The task_manager instance is passed from the expiration_manager_loop
        await self.evaluate_queue(task_manager=task_manager)

    async def activate(self, task_manager):
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
        await self.doc.fetch_all_links()
        if self.doc.task_state == TaskState.PENDING:
            logger.warning(
                f"Task '#{self.doc.id}' is already pending, not activating it again.")
            # Under premise that the task is ONLY activated in this method, we can skip it
            return

        assert (self.doc.task_state == TaskState.QUEUED
                ), f"Task '#{self.doc.id}' is not queued, but in state {self.doc.task_state}."

        session = Session(self.doc.assigned_session if self.doc.task_type !=
                          TaskType.RESERVATION else None)

        # No task activation happens for a stale locker
        if self.doc.assigned_locker and self.doc.assigned_locker.locker_state == LockerState.STALE:
            # workarounds so .complete does not complain
            self.doc.task_state = TaskState.PENDING
            self.doc.expires_at = datetime.now(timezone.utc)
            await self.complete(task_manager=task_manager)
            return

        if session.exists:
            # if (self.doc.target == TaskTarget.LOCKER and
            #        self.doc.task_type == TaskType.REPORT):
            #    # Wait for user to close locker
            #    task = await Task(TaskItemModel(
            #        target=TaskTarget.LOCKER,
            #        task_type=TaskType.REPORT,
            #        queued_state=session.next_state,
            #        assigned_session=session.doc,
            #        assigned_user=session.doc.assigned_user,
            #        assigned_station=session.doc.assigned_station,
            #        assigned_locker=session.doc.assigned_locker,
            #        timeout_states=[SessionState.EXPIRED],#

            #    )).insert()
            #    # await task.activate(task_manager=task_manager)

            await session.handle_task_activation(self.doc)

        # if session and not await session.handle_task_activation(self.doc):
        #    # workarounds so .complete does not complain
        #   self.doc.task_state = TaskState.PENDING
        #    self.doc.expires_at = datetime.now()
        #    await self.complete(task_manager=task_manager)

        # Calculate task properties
        now = datetime.now(timezone.utc)
        timeout_window = self.timeout_window
        timeout_date = now + timedelta(seconds=timeout_window)

        self.doc.activated_at = now
        if self.doc.task_state != TaskState.COMPLETED:
            self.doc.task_state = TaskState.PENDING
            self.doc.expires_at = timeout_date
            self.doc.expiration_window = timeout_window
        else:
            self.doc.expires_at = now
            self.doc.expiration_window = timedelta(seconds=0)

        await self.doc.save_changes()
        task_manager.restart()

    async def complete(self, task_manager):
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
        assert (self.doc.task_state == TaskState.PENDING
                ), f"Cannot complete Task '#{self.doc.id}' as it is in {self.doc.task_state}."

        assert (datetime.now(timezone.utc) < self.doc.expires_at.replace(tzinfo=timezone.utc) + timedelta(seconds=1)
                ), "Task has already expired."
        # Update task state
        self.doc.completed_at = datetime.now(timezone.utc)
        self.doc.task_state = TaskState.COMPLETED
        await self.doc.save_changes()

        if self.doc.target == TaskTarget.TERMINAL and self.doc.task_type == TaskType.REPORT:
            self.doc.assigned_session.timeout_count = 0
            await self.doc.assigned_session.save_changes()

        await self.evaluate_queue(task_manager=task_manager)

    async def cancel(self, task_manager):
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
                await Task(TaskItemModel(
                    target=TaskTarget.TERMINAL,
                    task_type=TaskType.CONFIRMATION,
                    assigned_user=self.doc.assigned_user,
                    assigned_session=self.doc.assigned_session,
                    assigned_station=self.doc.assigned_station,
                    queued_state=TerminalState.IDLE,
                    timeout_states=[SessionState.ABORTED],
                )).insert()

        # If the task targeted an open locker, send an instruction for it to be locked
        elif self.doc.target == TaskTarget.LOCKER:
            await self.doc.fetch_all_links()
            if self.doc.assigned_locker.locker_state == LockerState.UNLOCKED:
                await Task(TaskItemModel(
                    target=TaskTarget.LOCKER,
                    task_type=TaskType.REPORT,
                    assigned_user=self.doc.assigned_user,
                    assigned_session=self.doc.assigned_session,
                    assigned_station=self.doc.assigned_station,
                    assigned_locker=self.doc.assigned_locker,
                    timeout_states=[SessionState.EXPIRED],
                    queued_state=LockerState.LOCKED
                )).insert()

        await self.evaluate_queue(task_manager=task_manager)
        task_manager.restart()
