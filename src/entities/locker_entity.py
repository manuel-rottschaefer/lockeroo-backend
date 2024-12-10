"""This module provides utilities for  database for lockers."""

# Types
from beanie import PydanticObjectId as ObjId, SortDirection
from beanie.operators import In, NotIn

# Entities
from src.entities.entity_utils import Entity
from src.models.locker_models import LockerModel, LockerStates, LockerType
from src.models.session_models import SessionModel, SessionStates, ACTIVE_SESSION_STATES
# Models
from src.models.station_models import StationModel
# Services
from src.services.logging_services import logger
from src.services.mqtt_services import fast_mqtt


class Locker(Entity):
    """Add behaviour to a locker instance."""
    @classmethod
    async def fetch(
        cls,
        locker_id: ObjId = None,
        station: StationModel = None,
        call_sign: str = '',
        index: int = None,
        with_linked: bool = False
    ):
        """Create a Locker instance and fetch the object asynchronously."""
        instance = cls()

        if locker_id is not None:
            instance.document = await LockerModel.get(locker_id)
        elif None not in [station, index]:
            instance.document = await LockerModel.find_one(
                LockerModel.station.id == station.id,  # pylint: disable=no-member
                LockerModel.station_index == index,
                fetch_links=True
            )
        elif None not in [call_sign, index]:
            instance.document = await LockerModel.find_one(
                LockerModel.station.call_sign == call_sign,  # pylint: disable=no-member
                LockerModel.station_index == index,
                fetch_links=True
            )
        if not instance.document:
            logger.info("Locker '#%s' not found at station '%s'.",
                        index, station)

        if with_linked:
            await instance.document.fetch_all_links()

        return instance

    @classmethod
    async def find_available(cls, station: StationModel, locker_type: LockerType):
        """Find an available locker at this station."""
        instance = cls()

        # 1. Find a stale session at this station
        stale_session = await SessionModel.find_one(
            SessionModel.assigned_station.id == station.id,  # pylint: disable=no-member
            SessionModel.assigned_locker.locker_type == locker_type.name,  # pylint: disable=no-member
            SessionModel.session_state == SessionStates.STALE,
            fetch_links=True
        ).sort(SessionModel.created_ts, SortDirection.ASCENDING)

        if stale_session:
            instance.document = await LockerModel.get(stale_session.assigned_locker.id)
            return instance

        # 2. Find all active sessions at this station
        active_sessions = await SessionModel.find(
            SessionModel.assigned_station.id == station.id,  # pylint: disable=no-member
            In(SessionModel.session_state, ACTIVE_SESSION_STATES),
            fetch_links=True
        ).to_list()
        active_lockers = [
            session.assigned_locker.id for session in active_sessions]
        
        # 3: Find a locker at this station that matches the type and does not belong to such a session
        available_locker: LockerModel = await LockerModel.find_one(
            # LockerModel.station.id == station.id,  # pylint: disable=no-member
            LockerModel.locker_type == locker_type.name,
            NotIn(LockerModel.id,  active_lockers),
            fetch_links=True
        ).sort(LockerModel.total_session_count, SortDirection.ASCENDING)
        if available_locker:
            instance.document = available_locker

        return instance

    @property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.document is not None

    async def register_state(self, state: LockerStates):
        """Update the reported (actual) locker state"""
        self.document.reported_state = state

    async def set_state(self, state: LockerStates):
        """Send a message to the station to unlock the locker."""
        await self.document.fetch_link(LockerModel.station)
        fast_mqtt.publish(
            f'stations/{self.station.call_sign}/locker/{self.station_index}/instruct', state.value)
