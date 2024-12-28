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
    FOLLOW_UP_STATES,
    SessionModel,
    SessionState,
    SessionView,
    CreatedSessionView,
    WebsocketUpdate)
# Models
from src.models.station_models import StationModel
from src.models.user_models import UserModel
# Services
from src.services import websocket_services
from src.services.logging_services import logger


class Session(Entity):
    """Add behaviour to a session instance."""
    doc: SessionModel

    @property
    async def view(self) -> SessionView:
        # await self.doc.fetch_all_links()
        # TODO: Improve this
        return SessionView(
            id=str(self.doc.id),
            assigned_station=str(self.doc.assigned_station.id),
            user=self.doc.user.fief_id,
            station_index=self.doc.assigned_locker.station_index if self.assigned_locker else None,
            session_type=self.doc.session_type,
            session_state=self.doc.session_state,
            websocket_token=self.doc.websocket_token,
        )

    @property
    def created_view(self) -> CreatedSessionView:
        """Return a view of the session that is suitable for creation."""
        return CreatedSessionView(
            id=str(self.doc.id),
            user=self.doc.user.fief_id,
            assigned_station=str(self.doc.assigned_station.id),
            station_index=self.doc.assigned_locker.station_index,
            session_type=self.doc.session_type,
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
        completed_action: ActionModel = await ActionModel.find_one(
            ActionModel.assigned_session.id == self.id,  # pylint: disable=no-member
            ActionModel.action_type == SessionState.COMPLETED.name,
            fetch_links=True
        )

        return completed_action.timestamp - self.doc.created_at

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
        async for action in ActionModel.find(ActionModel.assigned_session == self.id).sort(
            ActionModel.timestamp
        ):
            if action.action_type in SessionState.ACTIVE:
                cycle_start = action.timestamp
            elif action.action_type in hold_states:
                active_duration += action.timestamp - cycle_start
                return active_duration

    @ property
    async def next_state(self) -> SessionState:
        """Return the next logical state of the session."""
        return FOLLOW_UP_STATES[self.session_state]

    async def broadcast_update(self) -> None:
        """Send a websocket update to the client."""
        await websocket_services.send_dict(
            self.doc.id, WebsocketUpdate(**self.doc.model_dump()).model_dump())

    def set_state(self, state: SessionState) -> None:
        """Set the state of the session."""
        self.doc.session_state = state
        logger.debug(
            f"Session '#{self.doc.id}' set to {self.doc.session_state}.")

    async def handle_conclude(self) -> None:
        """Calculate and store statistical data when session completes/expires/aborts."""
        total_duration: timedelta = await self.total_duration

        # Update session state
        self.set_state(SessionState.COMPLETED)
        await self.broadcast_update()
        self.doc.total_duration = total_duration
        await self.doc.save_changes()

        # Update station statistics
        await self.assigned_station.inc(
            {StationModel.total_session_count: 1,
             StationModel.total_session_duration: total_duration})
        # Update locker statistics
        await self.assigned_locker.inc(
            {LockerModel.total_session_count: 1,
             LockerModel.total_session_duration: total_duration})
        # Update user statistics
        await self.doc.user.inc({
            UserModel.total_session_count: 1,
            UserModel.total_session_duration: total_duration})
