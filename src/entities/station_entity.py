"""This module provides utilities for  database for stations."""

# Basics
from typing import Optional

# Beanie
from beanie import PydanticObjectId as ObjId, SortDirection
from beanie.operators import Set


# Entities
from src.entities.entity_utils import Entity
from src.entities.locker_entity import Locker

# Models
from src.models.session_models import SessionModel, SessionStates
from src.models.station_models import StationModel, StationStates, TerminalStates
from src.models.locker_models import LockerModel

# Services
from src.services.maintenance_services import has_scheduled

# Logging
from src.services.logging_services import logger


class Station(Entity):
    """Adds behaviour for a station instance."""
    @classmethod
    async def find(
        cls,
        station_id: Optional[ObjId] = None,
        call_sign: Optional[str] = None,
        station_state: Optional[StationStates] = None,
        terminal_state: Optional[TerminalStates] = None,
    ):
        """Find a session in the database"""
        instance = cls()

        query = {
            StationModel.id: station_id,
            StationModel.call_sign: call_sign,
            StationModel.station_state: station_state,
            StationModel.terminal_state: terminal_state,
        }

        # Filter out None values
        query = {k: v for k, v in query.items() if v is not None}

        station_item: StationModel = await StationModel.find(
            query, fetch_links=True
        ).sort((SessionModel.created_ts, SortDirection.DESCENDING)).first_or_none()

        instance.document = station_item if station_item else None
        return instance

    ### Attributes ###
    @property
    def exists(self) -> bool:
        """Check whether the station entity has a document."""
        return self.document is not None

    @property
    async def is_available(self) -> bool:
        """Check whether the station is available for new sessions at the moment.
        This method shall not check locker availability."""
        # 1: Check whether the station is marked as unavailable
        if not self.station_state == StationStates.AVAILABLE:
            return False

        # 2: Check whether there is a planned maintenance in 3 hours
        if await has_scheduled(self.id):
            return False

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
                          LockerModel.station == self.id,
                          LockerModel.station_index == index,
                      )
                      )
    ### Terminal setters ###

    async def register_station_state(
        self: StationModel, new_station_state: StationStates
    ) -> StationStates:
        """Update the state of a station.
        No checks are performed here, as the request is assumed to be valid."""
        await self.document.update(Set({StationModel.station_state: new_station_state}), skip_actions=['notify_station_state'])
        logger.debug(f"Station '{self.call_sign}' state set to {
                     self.station_state}.")
        return new_station_state

    async def register_terminal_state(
        self: StationModel, new_terminal_state: TerminalStates = None
    ) -> None:
        """Update the terminal state of a station. This function either accepts a TerminalState or a SessionState. """
        await self.document.update(Set({StationModel.terminal_state: new_terminal_state}),
                                   skip_actions=['notify_station_state'])
        logger.debug(
            f"Terminal at station '{self.id}' set to {
                self.terminal_state}."
        )

    async def activate_payment(self):
        """Activate a payment process at the station."""
        await self.document.update(
            Set({StationModel.terminal_state: TerminalStates.PAYMENT}),
            skip_actions=['notify_station_state'])

    async def increase_completed_sessions_count(self: StationModel):
        """Increase the count of completed sessions at the station.
        No checks are performed here, as the request is assumed to be valid."""
        await self.document.update(Set({StationModel.total_sessions: self.total_sessions + 1}))
