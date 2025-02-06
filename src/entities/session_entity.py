"""This module provides utilities for  database for sessions."""
# Basics
from datetime import datetime, timedelta
# Types
from typing import List
# Entities
from src.entities.entity_utils import Entity
from src.models.action_models import ActionModel
from src.models.locker_models import LockerModel
from src.models.session_models import (
    SESSION_STATE_FLOW,
    SessionModel,
    SessionState,
    SessionView,
    CreatedSessionView,
    WebsocketUpdate)
# Models
from src.models.station_models import StationModel
from src.models.user_models import UserModel
from src.models.task_models import TaskItemModel
# Services
from src.services import websocket_services
from src.services.logging_services import logger_service as logger
# Exceptions
from src.exceptions.session_exceptions import SessionNotFoundException


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
    async def view(self) -> SessionView:
        # await self.doc.fetch_all_links()
        # TODO: Improve this
        return SessionView(
            id=self.doc.id,
            station=str(self.doc.assigned_station.id),
            assigned_user=self.doc.assigned_user.fief_id,
            locker_index=self.doc.assigned_locker.station_index if self.assigned_locker else None,
            service_type=self.doc.session_type,
            session_state=self.doc.session_state,
            websocket_token=self.doc.websocket_token,
        )

    @property
    def created_view(self) -> CreatedSessionView:
        """Return a view of the session that is suitable for creation."""
        return CreatedSessionView(
            id=self.doc.id,
            assigned_user=self.doc.assigned_user.fief_id,
            station=str(self.doc.assigned_station.id),
            locker_index=self.doc.assigned_locker.station_index,
            service_type=self.doc.session_type,
            session_state=self.doc.session_state,
            websocket_token=self.doc.websocket_token,
        )

    ### Calculated Properties ###

    @ property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.doc is not None

    @ property
    async def total_duration(self) -> timedelta:
        """Returns the amount of seconds between session creation and completion or now."""
        # Return the seconds since the session was created if it is still running
        if self.doc.session_state != SessionState.COMPLETED:
            return datetime.now() - self.doc.created_at

        # Otherwise, return the seconds between creation and completion
        return self.doc.completed_at - self.doc.created_at

    @ property
    async def active_duration(self) -> timedelta:
        """Returns the amount of seconds the session has been active until now,
        i.e time that the user gets charged for."""

        # Collect all actions of the session
        active_duration: timedelta = timedelta(minutes=0)
        cycle_start: datetime = None

        hold_states: List[SessionState] = [
            SessionState.HOLD,
            SessionState.PAYMENT,
        ]

        # Sum up time between all locked cycles
        async for action in ActionModel.find(
            ActionModel.assigned_session == self.id
        ).sort(ActionModel.timestamp):
            if action.action_type in SessionState.ACTIVE:
                cycle_start = action.timestamp
            elif action.action_type in hold_states:
                active_duration += action.timestamp - cycle_start
        return active_duration

    @ property
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
        logger.debug(
            f"Session '#{self.doc.id}' set to {self.doc.session_state}.")

    async def handle_conclude(self) -> None:
        """Calculate and store statistical data when session completes/expires/aborts."""
        self.doc.total_duration = await self.total_duration
        await self.doc.fetch_all_links()
        # TODO: List these categories only for completed sessions?
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

        await self.doc.save_changes()
