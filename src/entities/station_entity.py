"""
Lockeroo.station_entity
-------------------------
This module provides the Station Entity class

Key Features:
    - Provides a functionality wrapper for Beanie Documents

Dependencies:
    - beanie
"""
# Beanie
from beanie import SortDirection
from beanie.operators import In, Or
# Entities
from src.entities.entity import Entity
# Models
from lockeroo_models.locker_models import (
    LockerModel,
    LockerAvailability,
    ReducedLockerAvailabilityView)
from lockeroo_models.session_models import (
    SessionModel,
    SessionState,
    ACTIVE_SESSION_STATES)
from lockeroo_models.station_models import (
    StationModel,
    StationState,
    TerminalState)
# Services
from src.services.mqtt_services import fast_mqtt
from src.services.logging_services import logger_service as logger
# Exceptions
from src.exceptions.station_exceptions import StationNotFoundException


class Station(Entity):
    """
    Lockeroo.Station
    -------
    A class representing a Station. A Station is a physical device containing lockers.
    Besides users, they are the main communication partner with the backend.

    Key Features:
    - `__init__`: Initializes a payment object and adds event logic to it
    - 'is_available': Returns whether a the station is generally available for new sessions
    - 'active_session_count': Returns the amount of active sessions
    - 'total_completed_session_count': Returns the amount of completed sessions
    - 'get_available_lockers': Returns a list of available lockers
    - 'instruct_terminal_state': Sends an instruction for a terminal state to the station
    - 'register_station_state': Stores a reported station state
    - 'register_terminal_state': Stores a reported terminal state
    """
    doc: StationModel

    def __init__(self, document=None, callsign=None):
        if document is None:
            raise StationNotFoundException(
                callsign=callsign,)
        super().__init__(document)
        self._add_handlers()

    def _add_handlers(self):
        def notify_station_state_logic(station: StationModel):
            """Send an update message regarding the session state to the mqtt broker."""
            fast_mqtt.publish(
                f"stations/{station.callsign}/state", station.station_state)

        StationModel.notify_station_state = notify_station_state_logic

    @property
    async def is_available(self) -> bool:
        """ Checks whether the station is available for new sessions.
        This is being determined based on the StationState of the Station

        Args:
            - self [Station]: The Station Entity

        Returns:
            - bool: Whether the station is available for sessions

        Raises:
            -

        Example:
            >>> station.is_available()
            True
        """
        # 1: Check whether the station is marked as unavailable
        if not self.station_state == StationState.AVAILABLE:
            return False

        # 2: Check whether there is a planned maintenance in 3 hours
        # TODO: Resolve circular import
        # if await has_scheduled(self.id):
        #    return False

        return True

    @property
    async def active_session_count(self) -> int:
        """ Returns the amount of active sessions at the station

        Args:
            - self [Station]: The Station Entity

        Returns:
            - int: The amount of active sessions at the station

        Raises:
            -

        Example:
            >>> station.active_session_count()
            8
        """
        session_count: int = await SessionModel.find(
            SessionModel.assigned_station.id == self.doc.id,
            SessionModel.session_state != SessionState.COMPLETED
        ).count()
        return session_count

    @property
    async def completed_session_count(self) -> int:
        """ Returns the amount of completed sessions at the station

        Args:
            - self [Station]: The Station Entity

        Returns:
            -

        Raises:
            -

        Example:
            >>> station.completed_session_count()
            240
        """
        session_count: int = await SessionModel.find(
            SessionModel.assigned_station.id == self.doc.id,
            SessionModel.session_state == SessionState.COMPLETED
        ).count()
        return session_count

    async def get_available_lockers(self) -> list[ReducedLockerAvailabilityView]:
        """ Returns the amount of available lockers at the station

        Args:
            - self [Station]: The Station Entity

        Returns:
            - list[ReducedLockerAvailabilityView]: A list of available lockers, if any

        Raises:
            -

        Example:
            >>> station.get_available_lockers()
            list[ReducedLockerAvailabilityView]
        """

        # Get all lockers at this station
        all_station_lockers = await LockerModel.find(
            LockerModel.station.id == self.doc.id,  # pylint: disable=no-member
            LockerModel.availability == LockerAvailability.OPERATIONAL,
            fetch_links=True
        ).sort(
            (LockerModel.total_session_count, SortDirection.ASCENDING)
        ).project(ReducedLockerAvailabilityView).to_list()  # pylint: disable=no-member

        # Get active sessions for this station
        # TODO: Project here for better performance
        active_sessions = await SessionModel.find(
            SessionModel.assigned_station.id == self.doc.id,  # pylint: disable=no-member
            Or(In(SessionModel.session_state, ACTIVE_SESSION_STATES),
                SessionModel.session_state == SessionState.STALE),
            fetch_links=True
        ).to_list()

        # Get IDs of lockers that are currently in use
        active_lockers = [s.assigned_locker.id for s in active_sessions]

        # Verify we don't have more active lockers than exist
        assert (len(all_station_lockers) >= len(active_lockers)
                ), (f"Found {len(active_lockers)} active lockers, but only "
                    f"{len(all_station_lockers)} lockers exist at station '#{self.callsign}'.")

        # Filter out lockers that are in use
        available_lockers = [
            locker for locker in all_station_lockers
            if str(locker.id) not in active_lockers
        ]

        return available_lockers

    ### Terminal setters ###

    async def instruct_terminal_state(self, terminal_state: TerminalState):
        """ Sends an instruction to a station regarding the terminal state

        Args:
            - self [Station]: The Station Entity
            - session_state [sessionState]: Contains the information for the locker state

        Returns:
            -

        Raises:
            -

        Example:
            >>> station.instruct_terminal_state(TerminalState.Verification)
            None
        """

        if terminal_state == self.doc.terminal_state:
            # TODO: Add handler here
            return

        logger.debug((
            f"Sending instruction '{terminal_state}' "
            f"to terminal at station '#{self.doc.callsign}'"))
        fast_mqtt.publish(
            message_or_topic=(
                f"stations/{self.doc.callsign}/instruct"), qos=2,
            payload=terminal_state.upper())

    async def register_station_state(
        self: StationModel, new_station_state: StationState
    ):
        """ Saves a reported station state for a station

        Args:
            - self [Station]: The Station Entity
            - new_station_state: The reported station state

        Returns:
            -

        Raises:
            -

        Example:
            >>> station.register_station_state(StationState.AVAILABLE)
            None
        """
        self.doc.station_state = new_station_state
        await self.doc.save_changes(
            skip_actions=['notify_station_state', 'instruct_terminal_state'])

    async def register_terminal_state(
        self: StationModel, new_terminal_state: TerminalState
    ):
        """ Saves a reported terminal state for a station

        Args:
            - self [Station]: The Station Entity
            - new_terminal_state [TerminalState]: The reported terminal state

        Returns:
            -

        Raises:
            -

        Example:
            >>> station.register_terminal_state(TerminalState.VERIFICATION)
            None
        """
        self.doc.terminal_state = new_terminal_state
        await self.doc.save_changes(
            skip_actions=['notify_station_state', 'instruct_terminal_state'])
        logger.debug((
            f"Terminal at station '#{self.callsign}' "
            f"set to {self.terminal_state}."
        ))
