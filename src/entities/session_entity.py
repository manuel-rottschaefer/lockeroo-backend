"""
Lockeroo.session_entity
-------------------------
This module provides the Session Entity class

Key Features:
    - Provides a functionality wrapper for Beanie Documents

Dependencies:
    - typing
"""
# Basics
from datetime import datetime, timedelta, timezone
from typing import List
# Beanie
from beanie import SortDirection
from beanie.operators import In
# Entities
from src.entities.entity import Entity
from src.entities.snapshot_entity import Snapshot
from src.entities.locker_entity import Locker
from src.entities.station_entity import Station
# Models
from lockeroo_models.snapshot_models import SnapshotModel
from lockeroo_models.locker_models import LockerModel, LockerState
from lockeroo_models.station_models import StationModel, TerminalState
from lockeroo_models.user_models import UserModel
from lockeroo_models.task_models import (
    TaskItemModel,
    TaskTarget,
    TaskState)
from lockeroo_models.session_models import (
    SESSION_STATE_FLOW,
    ACTIVE_SESSION_STATES,
    SessionModel,
    SessionState,)
# Services
from src.services.websocket_services import websocketmanager
from src.services.logging_services import logger_service as logger


class Session(Entity):
    """
    Lockeroo.Session
    -------
    A class representing a Session. A Session represents a complete usage cycle,
    from requesting the session, using the locker, to payment and completion

    Key Features:
    - `__init__`: Initializes a Session object and adds event logic to it
    - 'set_state': Sets a (new) state for the session
     - 'next_state': Returns the next logical state of the session
    - 'calc_total_duration': Returns the total duration of the session
    - 'calc_active_duration': Returns the active duration of the session
    - 'broadcast_update': Sends the current session state to the beloning websocket channel
    - 'handle_task_activation': Applies logical actions based on the session's current state
    """
    doc: SessionModel

    def __init__(self, document=None, user_id=None):
        super().__init__(document)
        self._add_handlers()

    def set_state(self, state: SessionState):
        """Set the new state of a session

        Args:
            - self [Session]: The Session Entity

        Returns:
            -

        Raises:
            -

        Example:
            >>> session.set_state(SessionState.Active)
            None
        """
        if state == self.doc.session_state:
            logger.warning(
                f"Session '#{self.doc.id}' is already in state {state}")
            return
        self.doc.session_state = state
        logger.info(
            f"Session '#{self.doc.id}' set to {self.doc.session_state}.", session_id=self.doc.id)  # pylint: disable=no-member

    @property
    def next_state(self) -> SessionState:
        """Gets the next logical state of a session

        Args:
            - self [Session]: The Session Entity

        Returns:
            Sessionstate

        Raises:
            -

        Example:
            >>> session.next_state()
            SessionState.ACTIVE
        """
        return SESSION_STATE_FLOW[self.session_state]

    def _add_handlers(self):
        async def handle_creation_logic(session: SessionModel):
            """Implementation of session creation handler"""
            await session.fetch_link(SessionModel.assigned_locker)
            logger.debug(
                (f"Created session at locker "  # pylint: disable=no-member
                    f"'#{session.assigned_locker.id}' "  # pylint: disable=no-member
                    f"('{session.assigned_station.callsign}')."), session_id=session.id)  # pylint: disable=no-member

            session.created_at = datetime.now(timezone.utc)
            session.websocket_token = websocketmanager.generate_token()
            await session.save_changes()

        SessionModel.handle_creation = handle_creation_logic

    async def calc_durations(self):
        """Calculates the total and active durations of a session

        Args:
            - self [Session]: The Session Entity

        Returns:
            - 

        Raises:
            -

        Example:
            >>> session.total_duration()
            timedelta(hours=2, minutes=24, seconds=48)
        """
        # Calculate the total duration of the session
        if self.doc.concluded_at is None:
            self.doc.concluded_at = datetime.now(timezone.utc)
        elif not self.doc.concluded_at:
            self.doc.concluded_at = datetime.now(timezone.utc)
        self.doc.total_duration = self.doc.concluded_at.replace(tzinfo=timezone.utc) - \
            self.doc.created_at.replace(tzinfo=timezone.utc)

        # Calculate the active duration of the session
        total_active_duration: timedelta = timedelta(minutes=0)
        cycle_start: datetime = None

        hold_states: List[SessionState] = [
            SessionState.HOLD,
            SessionState.PAYMENT]

        # Sum up time between all active cycles
        snaps: List[SnapshotModel] = await SnapshotModel.find(
            SnapshotModel.assigned_session.id == self.doc.id
        ).sort((SnapshotModel.timestamp, SortDirection.ASCENDING)).to_list()

        if not snaps:
            logger.debug(f"No snapshots found for session '#{self.doc.id}'")
            self.doc.active_duration = total_active_duration
            return total_active_duration

        for snap in snaps:
            if snap.session_state in ACTIVE_SESSION_STATES:
                cycle_start = snap.timestamp.replace(tzinfo=timezone.utc)
            elif snap.session_state in hold_states and cycle_start is not None:
                time_diff = snap.timestamp.replace(
                    tzinfo=timezone.utc) - cycle_start

                total_active_duration += time_diff
                cycle_start = None  # Reset cycle_start after using it

        # Handle case where session is currently active but hasn't ended
        if cycle_start is not None and self.doc.session_state in ACTIVE_SESSION_STATES:
            current_time = datetime.now(timezone.utc)
            time_diff = current_time - cycle_start.replace(tzinfo=timezone.utc)

            total_active_duration += time_diff

        self.doc.active_duration = total_active_duration
        await self.doc.save_changes()

    async def _broadcast_update(self, task: TaskItemModel = None):
        """ Send a session status update to the belonging websocket session

        Args:
            - self [Session]: The Session Entity
            - task [TaskItemModel]: The task which initiated the update call

        Returns:
            -

        Raises:
            -

        Example:
            >>> session.broadcast_update(TaskItemModel({}))
        """
        # logger.debug(
        #    f"Broadcasting update for session '#{self.doc.id}' "
        #    f"to websocket client '{self.doc.websocket_token}'.")
        expiration_date: datetime = getattr(task, 'expires_at', None)
        expiration_ts: float = expiration_date.timestamp() if expiration_date else None

    async def handle_task_activation(self, task: TaskItemModel) -> bool:
        """ Inititates followup logic when a task is activated.

        Args:
            - self [Session]: The Session Entity
            - task [TaskItemModel]: The task that was activated

        Returns:
            - bool: Whether a followup task has to be inititated

        Raises:
            -

        Example:
            >>> session.handle_task_activation(TaskItemModel({}))
            True
        """
        # Move task to next session state
        if isinstance(task.queued_state, SessionState):
            self.set_state(task.queued_state)
            await self.doc.save_changes()
            await Snapshot(SnapshotModel(
                timestamp=datetime.now(timezone.utc),
                assigned_session=self.doc,
                session_state=task.queued_state
            )).insert()

        # Instruct terminal state in order to arrive at upcoming session state
        if isinstance(task.queued_state, TerminalState):
            station: Station = Station(self.doc.assigned_station)
            await station.instruct_terminal_state(task.queued_state)

        # Instruct locker state in order to arrive at upcoming session state
        if isinstance(task.queued_state, LockerState):
            locker: Locker = Locker(task.assigned_locker)
            # Check if the locker should be locked
            # TODO: What is this for?
            # if (locker.locker_state != LockerState.LOCKED and
            #        locker.locker_state != LockerState.STALE):
            #    raise InvalidLockerStateException(
            #        locker_id=locker.doc.id,
            #        actual_state=locker.doc.locker_state,
            #        expected_state=LockerState.LOCKED,
            #        raise_http=False)

            # Stale lockers do not receive new instructions
            if locker.doc.locker_state == LockerState.LOCKED:
                await locker.instruct_state(LockerState.UNLOCKED, task)

    async def handle_conclude(self, final_state: SessionState):
        """Calculates and saves relevant data when a session concludes, meaning it
        either ended successfully or was moved to a unsuccessful state

        Args:
            - self [Session]: The Session Entity
            - final_state [Sessionstate]: The final state that the session will take on

        Returns:
            -

        Raises:
            -

        Example:
            >>> session.handle_conclude()
            None
        """
        self.set_state(final_state)
        self.doc.concluded_at = datetime.now(timezone.utc)
        await self.calc_durations()

        # Stop queued tasks
        pending_tasks: List[TaskItemModel] = await TaskItemModel.find(
            TaskItemModel.assigned_session.id == self.id,
            TaskItemModel.target == TaskTarget.USER,
            In(TaskItemModel.task_state, [
               TaskState.QUEUED, TaskState.PENDING]),
        ).to_list()

        for task in pending_tasks:
            task.task_state = TaskState.CANCELED
            await task.save_changes()
        if pending_tasks:
            logger.debug(
                f"Stopped {len(pending_tasks)} tasks for session '#{self.doc.id}'")

        await self.doc.fetch_all_links()
        # Update station statistics
        await self.assigned_station.inc(
            {StationModel.total_session_count: 1,
             StationModel.total_session_duration: self.doc.total_duration})
        # Update locker statistics
        await self.assigned_locker.inc(
            {LockerModel.total_session_count: 1,
             LockerModel.total_session_duration: self.doc.total_duration})
        # Update user statistics
        await self.doc.assigned_user.inc({
            UserModel.total_session_count: 1,
            UserModel.total_session_duration: self.doc.total_duration})

        await Snapshot(SnapshotModel(
            timestamp=self.doc.concluded_at,
            assigned_session=self.doc,
            session_state=SessionState.COMPLETED
        )).insert()
