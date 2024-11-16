"""Utilities for the station model"""

# Basics
from beanie import PydanticObjectId as ObjId

# Types
from typing import Optional

# Entities
from src.entities.locker_entity import Locker

# Models
from src.models.session_models import SessionModel, SessionStates
from src.models.station_models import StationModel, StationStates, TerminalStates
from src.models.locker_models import LockerModel

# Services
from src.services.exceptions import ServiceExceptions
from src.services.maintenance_services import has_scheduled

# Logging
from src.services.logging_services import logger


class Station():
    """Adds behaviour for a station instance."""

    def __getattr__(self, name):
        """Delegate attribute access to the internal document."""
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the internal document, except for 'document' itself"""
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    def __init__(self, document: StationModel = None):
        super().__init__()
        self.document = document

    @classmethod
    async def fetch(cls, station_id: ObjId = None, call_sign: str = None):
        """Create a Station instance and fetch the object asynchronously."""
        instance = cls()

        if station_id is not None:
            instance.document = await StationModel.get(station_id)
        elif call_sign is not None:
            instance.document = await StationModel.find_one(StationModel.call_sign == call_sign)
        else:
            logger.error("Failed to initialize Station Entity.")

        if instance.document is None:
            logger.error(
                "Failed to initialize Station Entity: No document found.")
            raise ValueError("Station document could not be found.")

        return instance

    ### Attributes ###
    @property
    async def is_available(self) -> bool:
        """Check whether the station is available for new sessions at the moment.
        This method shall not check locker availability."""
        # 1: Check whether the station is marked as unavailable
        if not self.station_state == StationStates.AVAILABLE:
            return False

        # 2: Check whether there is a planned maintenance in 3 hours
        elif await has_scheduled(self.id):
            return False

        else:
            return True

    @property
    async def total_completed_session_count(self) -> int:
        """Get the total amount of sessions conducted at this station, without active ones."""
        session_count: int = await SessionModel.find(
            SessionModel.assigned_station == self.document.id,
            SessionModel.session_state == SessionStates.COMPLETED
        ).count()
        return session_count

    @property
    async def active_session_count(self) -> int:
        """Get the total amount of currently active stations at this station."""
        session_count: int = await SessionModel.find(
            SessionModel.assigned_station == self.document.id,
            SessionModel.session_state != SessionStates.COMPLETED
        ).count()
        return session_count

    ### Locker management ###

    async def get_locker(self, index: int) -> Locker:
        """Find a locker at a station by index."""
        # 1: Find the locker
        return Locker(await
                      LockerModel.find_one(
                          LockerModel.parent_station == self.id,
                          LockerModel.station_index == index,
                      )
                      )

    async def find_available_locker(self, locker_type: str) -> Optional[LockerModel]:
        """This methods handles the locker selection process at a station."""
        # 1. Try to find a locker from stale a stale session
        stale_session = await SessionModel.find(
            SessionModel.assigned_station == self.id,
            SessionModel.session_state == SessionStates.STALE
        ).first_or_none()

        if stale_session:
            return await Locker().fetch(locker_id=stale_session.assigned_locker)

        # 2: If there is no stale locker, find a usual one
        locker: LockerModel = await LockerModel.find(
            LockerModel.parent_station == self.id,
            LockerModel.locker_type == locker_type
        ).sort(LockerModel.total_session_count).first_or_none()

        if not locker:
            logger.info(ServiceExceptions.LOCKER_NOT_AVAILABLE,
                        station=self.id)
            return None

        return locker

    ### Terminal setters ###

    async def set_station_state(
        self: StationModel, new_state: StationStates
    ) -> StationStates:
        """Update the state of a station.
        No checks are performed here, as the request is assumed to be valid."""
        self.document.station_state = new_state
        await self.replace(skip_actions=['notify_terminal_state'])
        logger.debug(f"Station '{self.call_sign}' state set to {
                     self.station_state}.")
        return new_state

    async def set_terminal_state(
        self: StationModel, terminal_state: TerminalStates = None, session_state: SessionStates = None
    ) -> StationStates:
        """Update the terminal state of a station. This function either accepts a TerminalState or a SessionState. """
        if terminal_state is None and session_state is not None:
            session_to_terminal_map: dict[SessionStates, TerminalStates] = {
                SessionStates.VERIFICATION: TerminalStates.VERIFICATION,
                SessionStates.PAYMENT: TerminalStates.PAYMENT
            }
            if session_state in session_to_terminal_map:
                terminal_state = session_to_terminal_map[session_state]

        self.document.terminal_state = terminal_state

        await self.document.replace(skip_actions=['notify_station_state'])
        logger.debug(
            f"Terminal at station '{self.call_sign}' set to {
                self.terminal_state}."
        )
        return terminal_state

    async def activate_payment(self):
        """Activate a payment process at the station."""
        self.document.terminal_state = TerminalStates.PAYMENT
        await self.document.replace(skip_actions=['notify_station_state'])

    async def increase_completed_sessions_count(self: StationModel):
        """Increase the count of completed sessions at the station.
        No checks are performed here, as the request is assumed to be valid."""
        self.document.total_sessions += 1
        await self.replace()
