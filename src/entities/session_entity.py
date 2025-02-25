"""This module provides utilities for  database for sessions."""
# Basics
from datetime import datetime, timedelta
# Types
from typing import List
# Entities
from src.entities.entity_utils import Entity
from src.entities.locker_entity import Locker
from src.entities.station_entity import Station
# Models
from src.models.action_models import ActionModel
from src.models.locker_models import LockerModel, LockerState
from src.models.task_models import (
    TaskItemModel,
    TaskTarget,
    TaskType)
from src.models.session_models import (
    SESSION_STATE_FLOW,
    SessionModel,
    SessionState,
    WebsocketUpdate)
from src.models.station_models import StationModel
from src.models.user_models import UserModel
# Services
from src.services import websocket_services
from src.services.logging_services import logger_service as logger
# Exceptions
from src.exceptions.session_exceptions import SessionNotFoundException
from src.exceptions.locker_exceptions import InvalidLockerStateException


class Session(Entity):
    """Add behaviour to a session instance."""
    doc: SessionModel

    def __init__(self, document=None, user_id=None):
        if document is None:
            raise SessionNotFoundException(
                user_id=user_id,
            )
        super().__init__(document)

    @property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.doc is not None

    @property
    async def calc_total_duration(self) -> timedelta:
        """Returns the amount of seconds between session creation and completion or now."""
        # Return the seconds since the session was created if it is still running
        if self.doc.session_state != SessionState.COMPLETED:
            return datetime.now() - self.doc.created_at

        # Otherwise, return the seconds between creation and completion
        if not self.doc.completed_at:
            self.doc.completed_at = datetime.now()
        self.doc.total_duration = self.doc.completed_at - self.doc.created_at
        return self.doc.total_duration

    @property
    async def calc_active_duration(self) -> timedelta:
        """Returns the amount of seconds the session has been active until now,
        i.e time that the user gets charged for."""

        # Collect all actions of the session
        active_duration: timedelta = timedelta(minutes=0)
        cycle_start: datetime = None

        hold_states: List[SessionState] = [
            SessionState.HOLD,
            SessionState.PAYMENT]

        # Sum up time between all locked cycles
        async for action in ActionModel.find(
            ActionModel.assigned_session == self.id
        ).sort(ActionModel.timestamp):
            if action.action_type in SessionState.ACTIVE:
                cycle_start = action.timestamp
            elif action.action_type in hold_states:
                active_duration += action.timestamp - cycle_start
        self.doc.active_duration = active_duration
        return self.doc.active_duration

    @property
    def next_state(self) -> SessionState:
        """Return the next logical state of the session."""

        return SESSION_STATE_FLOW[self.session_state]

    async def broadcast_update(self, task: TaskItemModel = None) -> None:
        """Send a websocket update to the client."""
        update_view = {
            "id": str(self.doc.id),
            "session_state": self.doc.session_state.value,
            "timeout": task.expires_at if task else None,
            "queue_position": task.queue_position if task else 0,
        }
        await websocket_services.send_dict(
            self.doc.id, WebsocketUpdate(**update_view).model_dump())

    def set_state(self, state: SessionState) -> None:
        """Set the state of the session."""
        self.doc.session_state = state
        logger.info(
            f"Session '#{self.doc.id}' set to {self.doc.session_state}.")

    async def activate(self, task: TaskItemModel) -> None:
        """Activate the session."""
        if (task.task_type == TaskType.REPORT
            and self.doc.session_state != SessionState.CANCELED
                and task.queued_state is not None):
            # Move session to next state
            self.set_state(task.queued_state)
            await self.doc.save_changes()
            await ActionModel(
                assigned_session=self.doc,
                action_type=task.queued_state
            ).insert()
            await self.broadcast_update(task)

        elif (task.task_type == TaskType.CONFIRMATION
              and task.target == TaskTarget.TERMINAL):
            if task.queued_state:
                self.set_state(task.queued_state)
                await self.doc.save_changes()
                await self.broadcast_update(task)
            if not task.is_expiration_retry:
                station: Station = Station(self.doc.assigned_station)
                await station.instruct_next_terminal_state(self.next_state)

        elif (task.task_type == TaskType.CONFIRMATION
              and task.target == TaskTarget.LOCKER):
            await task.fetch_link(TaskItemModel.assigned_locker)
            # Check if the locker still has a stale session
            # If that is the case, complete the session,
            # else send an unlock command to the locker
            locker: Locker = Locker(self.doc.assigned_locker)

            stale_session: SessionModel = await SessionModel.find(
                SessionModel.assigned_locker.id == locker.doc.id,  # pylint: disable=no-member
                SessionModel.session_state == SessionState.STALE,
            ).first_or_none()

            if stale_session:
                stale_session = Session(stale_session)
                stale_session.set_state(SessionState.COMPLETED)
                await stale_session.doc.save_changes()
                await stale_session.handle_conclude()
            elif (locker.doc.locker_state != LockerState.LOCKED):
                raise InvalidLockerStateException(
                    locker_id=locker.doc.id,
                    actual_state=locker.doc.locker_state,
                    expected_state=LockerState.LOCKED,
                    raise_http=False)
            else:
                # Send UNLOCK command to the locker
                await locker.instruct_state(LockerState.UNLOCKED)

    async def handle_conclude(self) -> None:
        """Calculate and store statistical data when session completes/expires/aborts."""
        self.doc.completed_at = datetime.now()
        await self.calc_total_duration
        await self.calc_active_duration
        await self.doc.save_changes()

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
