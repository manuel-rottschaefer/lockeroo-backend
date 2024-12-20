"""This module provides utilities for  database for lockers."""

# Types
from typing import Optional

# Beanie
from beanie import PydanticObjectId as ObjId, SortDirection
from beanie.operators import In, NotIn

# Entities
from src.entities.entity_utils import Entity
from src.models.locker_models import LockerModel, LockerStates, LockerTypes
from src.models.session_models import SessionModel, SessionStates, ACTIVE_SESSION_STATES
# Models
from src.models.station_models import StationModel
# Services
from src.services.logging_services import logger
from src.services.mqtt_services import fast_mqtt


class Locker(Entity):
    """Add behaviour to a locker instance."""
    document: LockerModel

    @classmethod
    async def find(
        cls,
        locker_id: Optional[ObjId] = None,
        station: Optional[ObjId] = None,
        station_callsign: Optional[str] = None,
        index: Optional[int] = None,
    ):
        """Find a locker in the database"""
        # TODO: The find methods should also handle exception cases
        instance = cls()

        query = {
            LockerModel.id: locker_id,
            LockerModel.station.id: station,  # pylint: disable=no-member
            LockerModel.station.callsign: station_callsign,  # pylint: disable=no-member
            LockerModel.station_index: index,  # pylint: disable=no-member
        }
        # Filter out None values
        query = {k: v for k, v in query.items() if v is not None}
        locker_item: LockerModel = await LockerModel.find(
            query, fetch_links=True
        ).sort((LockerModel.total_session_count, SortDirection.DESCENDING)).first_or_none()

        if locker_item:
            instance.document = locker_item
        return instance

    @classmethod
    async def find_available(cls, station: StationModel, locker_type: LockerTypes):
        """Find an available locker at this station."""
        instance = cls()

        # 1. Find a stale session at this station
        stale_session = await SessionModel.find(
            SessionModel.assigned_station.id == station.id,  # pylint: disable=no-member
            SessionModel.assigned_locker.locker_type == locker_type.name,  # pylint: disable=no-member
            SessionModel.session_state == SessionStates.STALE,
            fetch_links=True
        ).sort((SessionModel.created_ts, SortDirection.ASCENDING)).first_or_none()

        if stale_session:
            instance.document = await LockerModel.get(stale_session.assigned_locker.id)
            return instance

        # 2. Find all active sessions at this station
        active_sessions = await SessionModel.find(
            SessionModel.assigned_station.id == station.id,  # pylint: disable=no-member
            In(SessionModel.session_state, ACTIVE_SESSION_STATES),
            fetch_links=True
        ).sort((SessionModel.created_ts, SortDirection.ASCENDING)).to_list()
        active_lockers = [
            session.assigned_locker.id for session in active_sessions]
        # TODO: Create a station locker count key, it is useful for such tasks
        assert len(
            active_lockers) < 30, "Found more active lockers than exist at station."

        # 3: Find a locker at this station that matches the type and does not belong to such a session
        available_locker: LockerModel = await LockerModel.find(
            # LockerModel.station.id == station.id,  # pylint: disable=no-member
            LockerModel.locker_type == locker_type.name,
            NotIn(LockerModel.id,  active_lockers),
            fetch_links=True
        ).sort((LockerModel.total_session_count, SortDirection.ASCENDING)).first_or_none()
        if available_locker:
            instance.document = available_locker

        return instance

    @property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.document is not None

    async def register_state(self, state: LockerStates):
        """Update the reported (actual) locker state"""
        logger.debug(f"Locker '#{self.document.callsign.replace('#', '')}' ('{
                     self.document.id}') registered as: {state}.")
        self.document.reported_state = state
        await self.document.save_changes(skip_actions=['log_changes'])

    async def instruct_state(self, state: LockerStates):
        """Send a message to the station to unlock the locker."""
        # await self.document.fetch_link(LockerModel.station)
        logger.debug(
            (f"Sending {state} instruction to locker '#{self.document.id}' "
             f"at station '#{self.document.station.callsign}'."))
        fast_mqtt.publish(
            f'stations/{self.station.callsign}/locker/{self.station_index}/instruct', state.value)
