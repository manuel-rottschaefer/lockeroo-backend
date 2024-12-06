"""This module provides utilities for  database for sessions."""

# Basics
from datetime import datetime, timedelta
# Types
from typing import List, Optional
from uuid import UUID

# Beanie
from beanie import SortDirection, WriteRules
from beanie.operators import Set

# Entities
from src.entities.entity_utils import Entity
from src.models.action_models import ActionModel
from src.models.locker_models import LockerModel
# Models
from src.models.session_models import (PaymentTypes, SessionModel,
                                       SessionStates, SessionView)
from src.models.station_models import StationModel
from src.models.locker_models import LockerModel
from src.models.action_models import ActionModel
from src.models.account_models import AccountModel
from src.models.session_models import (SessionModel,
                                       SessionView,
                                       SessionStates)

# Entities
from src.entities.entity_utils import Entity

# Services
from src.services.logging_services import logger


class Session(Entity):
    """Add behaviour to a session instance."""
    @classmethod
    async def find(
        cls,
        session_id: Optional[str] = None,
        user: Optional[UserModel] = None,
        session_state: Optional[SessionStates] = None,
        session_active: Optional[bool] = None,
        assigned_station: Optional[StationModel] = None,
        locker_index: Optional[int] = None
    ):
        """Find a session in the database"""
        instance = cls()

        query = {
            SessionModel.id: session_id,
            SessionModel.user: user,
            SessionModel.session_state: session_state,
            SessionModel.is_active: session_active,
            SessionModel.assigned_station: assigned_station,
            SessionModel.assigned_locker.station_index: locker_index,  # pylint: disable=no-member
        }

        # Filter out None values
        query = {k: v for k, v in query.items() if v is not None}

        session_item: SessionModel = await SessionModel.find(
            query, fetch_links=True
        ).sort((SessionModel.created_ts, SortDirection.DESCENDING)).first_or_none()

        if session_item:
            instance.document = session_item
        return instance

    @classmethod
    async def create(
        cls,
        user: UserModel,
        station: StationModel,
        locker: LockerModel
    ):
        """Create a new session item and insert it into the database."""
        instance = cls()
        instance.document = SessionModel(
            user=user,
            assigned_station=station,
            assigned_locker=locker,
            session_state=SessionStates.CREATED,
            created_ts=datetime.now(),
        )
        await instance.document.insert(link_rule=WriteRules.WRITE)
        return instance

    @property
    async def view(self) -> SessionView:
        await self.document.fetch_all_links()
        return SessionView(
            id=self.id,
            assigned_station=self.assigned_station.id,
            user=self.user.fief_id,
            locker_index=self.assigned_locker.station_index if self.assigned_locker else None,
            session_type=self.session_type,
            session_state=self.session_state.name,
            created_ts=self.created_ts
        )

        ### Calculated Properties ###

    @ property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.document is not None

    @ property
    async def total_duration(self) -> timedelta:
        """Returns the amount of seconds between session creation and completion or now."""
        # Return the seconds since the session was created if it is still running
        if self.document.session_state != SessionStates.COMPLETED:
            return timedelta(datetime.now() - self.document.created_ts)

        # Otherwise, return the seconds between creation and completion
        completed: ActionModel = await ActionModel.find(
            ActionModel.assigned_session.id == self.id,  # pylint: disable=no-member
            ActionModel.action_type == SessionStates.COMPLETED.name,
            fetch_links=True
        ).first_or_none()

        return completed.timestamp - self.document.created_ts

    @ property
    async def active_duration(self) -> timedelta:
        """Returns the amount of seconds the session has been active until now,
        i.e time that the user gets charged for."""

        # Collect all actions of the session
        active_duration: timedelta = timedelta(minutes=0)
        cycle_start: datetime = None

        hold_states: List[SessionStates] = [
            SessionStates.HOLD,
            SessionStates.PAYMENT,
        ]

        # Sum up time between all locked cycles
        async for action in ActionModel.find(ActionModel.assigned_session == self.id).sort(
            ActionModel.timestamp
        ):
            if action.action_type in SessionStates.ACTIVE:
                cycle_start = action.timestamp
            elif action.action_type in hold_states:
                active_duration += action.timestamp - cycle_start
                return active_duration

    @ property
    async def next_state(self) -> SessionStates:
        """Return the next logical state of the session."""
        return getattr(SessionStates, self.session_state['next'])

    async def set_state(self, state: SessionStates) -> None:
        """Update the current state of a session."""
        try:
            self.document.session_state = state
            if state['is_active'] and not self.is_active:
                self.document.is_active = True
            elif not state['is_active'] and self.is_active:
                self.document.is_active = False
            logger.debug(
                f"Session '{self.id}' updated to {self.session_state}."
            )

        except (ValueError, TypeError) as e:
            logger.error(f"Failed to update state of session '{
                self.id}': {e}.")

    async def assign_payment_method(self, method: PaymentTypes):
        """Assign a payment method to a session."""
        try:
            self.document.payment_method = method
            logger.info(
                f"Payment method '{
                    self.payment_method}' assigned to session '{self.id}'."
            )
        except (ValueError, TypeError) as e:
            logger.error(
                f"Failed to assign payment method {
                    method} to session {self.id}: {e}"
            )

    async def handle_conclude(self):
        """Calculate and store statistical data when session completes/expires/aborts."""
        total_duration: timedelta = await self.total_duration
        await self.document.update(Set({
            SessionModel.total_duration: total_duration
        }))
        # Update station statistics
        await self.assigned_station.inc(
            {StationModel.total_sessions: 1,
             StationModel.total_session_duration: total_duration})
        # Update user statistics
        # TODO: Make this UserModel only
        if type(self.document.user.id) == UUID:
            return
            await self.document.account.inc(
                {AccountModel.total_sessions: 1,
                    AccountModel.total_session_duration: total_duration})
