"""This module provides utilities for  database for stations."""
# Entities
from src.entities.entity_utils import Entity
from src.entities.locker_entity import Locker
from src.models.locker_models import LockerModel
# Models
from src.models.session_models import SessionModel, SessionState
from src.models.station_models import (StationModel, StationStates,
                                       TerminalState)
# Logging
from src.services.logging_services import logger
# Services
from src.services.maintenance_services import has_scheduled


class Station(Entity):
    """Adds behaviour for a station instance."""
    doc: StationModel

    ### Attributes ###
    @property
    def exists(self) -> bool:
        """Check whether the station entity has a document."""
        return self.doc is not None

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
            SessionModel.assigned_station == self.doc.id,
            SessionModel.session_state == SessionState.COMPLETED
        ).count()
        return session_count

    @property
    async def active_session_count(self) -> int:
        """Get the total amount of currently active stations at this station."""
        session_count: int = await SessionModel.find(
            SessionModel.assigned_station == self.doc.id,
            SessionModel.session_state != SessionState.COMPLETED
        ).count()
        return session_count

    ### Locker management ###

    async def get_locker(self, index: int) -> Locker:
        """Find a locker at a station by index."""
        # 1: Find the locker
        return Locker(await
                      LockerModel.find_one(
                          LockerModel.station == self.id,
                          LockerModel.station_index == index,)
                      )

    async def get_available_lockers(self) -> list[Locker]:
        """Find all available lockers at a station."""
        # TODO: Implement and apply this method
        # 1: Find all lockers
        lockers = await LockerModel.find(
            LockerModel.station == self.id,
            LockerModel.is_available == True
        ).to_list()
        return [Locker(locker) for locker in lockers]
    ### Terminal setters ###

    async def register_station_state(
        self: StationModel, new_station_state: StationStates
    ) -> StationStates:
        """Update the state of a station.
        No checks are performed here, as the request is assumed to be valid."""
        self.doc.station_state = new_station_state
        await self.doc.save_changes(
            skip_actions=['notify_station_state', 'instruct_terminal_state'])
        return new_station_state

    async def register_terminal_state(
        self: StationModel, new_terminal_state: TerminalState = None
    ) -> None:
        """Update the terminal state of a station."""
        self.doc.terminal_state = new_terminal_state
        await self.doc.save_changes(
            skip_actions=['notify_station_state', 'instruct_terminal_state'])
        logger.debug(
            f"Terminal at station '#{self.callsign}' set to {
                self.terminal_state}."
        )

    async def activate_payment(self):
        """Activate a payment process at the station."""
        self.doc.terminal_state = TerminalState.PAYMENT
        await self.doc.save_changes(
            skip_actions=['notify_station_state', 'instruct_terminal_state'])

    async def increase_completed_sessions_count(self: StationModel):
        """Increase the count of completed sessions at the station.
        No checks are performed here, as the request is assumed to be valid."""
        self.doc.total_sessions += 1
        await self.doc.save_changes(
            skip_actions=['notify_station_state', 'instruct_terminal_state'])
