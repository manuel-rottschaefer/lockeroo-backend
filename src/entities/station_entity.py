"""This module provides utilities for  database for stations."""
# Beanie
from beanie import SortDirection
from beanie.operators import In, Or
# Entities
from src.entities.entity_utils import Entity
from src.models.locker_models import (
    LockerModel,
    LockerAvailability,
    ReducedLockerView)
# Models
from src.models.session_models import (
    SessionModel,
    ReducedSessionView,
    SessionState,
    ACTIVE_SESSION_STATES)
from src.models.station_models import (
    StationModel,
    StationState,
    TerminalState)
# Logging
from src.services.logging_services import logger_service as logger
# Exceptions
from src.exceptions.station_exceptions import StationNotFoundException
# Services
from src.services.maintenance_services import has_scheduled


class Station(Entity):
    """Adds behaviour for a station instance."""
    doc: StationModel

    def __init__(self, document=None, callsign=None):
        if document is None:
            raise StationNotFoundException(
                callsign=callsign,
            )
        super().__init__(document)

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
        if not self.station_state == StationState.AVAILABLE:
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

    async def get_available_lockers(self) -> list[ReducedLockerView]:
        """Find all available lockers at a station.
        Look for active sessions at the station, then filter out the lockers that are in use.
        Return the available lockers sorted by total session count."""

        # Get all lockers at this station
        all_station_lockers = await LockerModel.find(
            LockerModel.station.id == self.doc.id,  # pylint: disable=no-member
            LockerModel.availability == LockerAvailability.OPERATIONAL,
            fetch_links=True
        ).sort(
            (LockerModel.total_session_count, SortDirection.ASCENDING)
        ).project(ReducedLockerView).to_list()  # pylint: disable=no-member

        # Get active sessions for this station
        active_sessions = await SessionModel.find(
            SessionModel.assigned_station.id == self.doc.id,  # pylint: disable=no-member
            Or(In(SessionModel.session_state, ACTIVE_SESSION_STATES),
                SessionModel.session_state == SessionState.STALE),
            fetch_links=True
        ).project(ReducedSessionView).sort(
            (SessionModel.created_at, SortDirection.ASCENDING)).to_list()

        # Get IDs of lockers that are currently in use
        active_lockers = {
            session.assigned_locker for session in active_sessions}

        # Filter out lockers that are in use
        available_lockers = [
            locker for locker in all_station_lockers
            if locker.id not in active_lockers
        ]

        # Verify we don't have more active lockers than exist
        assert (len(all_station_lockers) >= len(active_lockers)
                ), (f"Found {len(active_lockers)} active lockers, but only "
                    f"{len(all_station_lockers)} lockers exist at station '#{self.callsign}'.")

        return available_lockers

    ### Terminal setters ###

    async def register_station_state(
        self: StationModel, new_station_state: StationState
    ) -> StationState:
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
