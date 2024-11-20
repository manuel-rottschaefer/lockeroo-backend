"""This module provides utilities for  database for sessions."""

# Basics
from datetime import datetime, timedelta
from uuid import UUID

# Types
from typing import List

# Beanie
from beanie import After, SortDirection, PydanticObjectId as ObjId
from beanie.operators import Set

# Models
from src.models.station_models import StationModel
from src.models.locker_models import LockerModel
from src.models.action_models import ActionModel
from src.models.session_models import (SessionModel,
                                       SessionPaymentTypes,
                                       SessionStates,)

# Services
from src.services.logging_services import logger
from src.services.exceptions import ServiceExceptions


class Session():
    """Add behaviour to a session instance."""

    def __getattr__(self, name):
        """Delegate attribute access to the internal document."""
        # TODO: If the session object itself is requested, return its document
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the internal document, except for 'document' itself."""
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    def __init__(self, document: SessionModel = None):
        super().__init__()
        self.document = document

    @classmethod
    async def fetch(
        cls,
        session_id: ObjId = None,
        locker: LockerModel = None,
        with_linked=False
    ):
        """Create a Session instance and fetch the object async."""
        instance = cls()
        if session_id is not None:
            instance.document = await SessionModel.get(session_id, ignore_cache=True)

        elif locker is not None:
            instance.document = await SessionModel.find(
                # TODO: The latest created session at a locker should also be the active one
                SessionModel.assigned_locker.id == locker.id,  # pylint: disable=no-member
                fetch_links=with_linked
            ).sort((SessionModel.created_ts, SortDirection.DESCENDING)).first_or_none()

        if not instance.exists:
            logger.info(ServiceExceptions.SESSION_NOT_FOUND,
                        session=session_id)
        return instance

    @classmethod
    async def create(
        cls, user_id: UUID,
        station: StationModel,
        locker: LockerModel
    ):
        '''Create a queue new session item and insert it into the database.'''
        instance = cls()
        instance.document = SessionModel(
            assigned_user=user_id,
            assigned_station=station,
            assigned_locker=locker,
            session_state=SessionStates.CREATED,
            created_ts=datetime.now(),
        )
        await instance.document.insert()
        return instance

    ### Calculated Properties ###

    @property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.document is not None

    @property
    def total_duration(self) -> int:
        """Returns the amount of seconds between session creation and completion or now."""
        return 0

    @property
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

    @property
    async def next_state(self) -> SessionStates:
        """Return the next logical state of the session."""
        return getattr(SessionStates, self.session_state['next'])

    async def set_state(self, state: SessionStates, notify: bool = True) -> None:
        """Update the current state of a session."""
        try:
            self.document.session_state = state
            if notify:
                await self.document.update(Set({SessionModel.session_state: state}))
            else:
                await self.document.update(
                    Set({SessionModel.session_state: state}), skip_actions=[After])

            logger.debug(
                f"Session '{self.id}' updated to state {self.session_state}."
            )

        except (ValueError, TypeError) as e:
            logger.error(f"Failed to update state of session '{
                         self.id}': {e}.")

    async def assign_payment_method(self, method: SessionPaymentTypes):
        """Assign a payment method to a session."""
        try:
            self.document.payment_method = method
            await self.replace(skip_actions=[After])
            logger.info(
                f"Payment method '{
                    self.payment_method}' assigned to session '{self.id}'."
            )
        except (ValueError, TypeError) as e:
            logger.error(
                f"Failed to assign payment method {
                    method} to session {self.id}: {e}"
            )
