"""This module provides utilities for  database for lockers."""

# Types
from beanie import PydanticObjectId as ObjId
from beanie.operators import Set, NotIn

# Models
from src.models.station_models import StationModel
from src.models.session_models import SessionModel, SessionStates
from src.models.locker_models import LockerModel, LockerStates

# Services
from src.services.logging_services import logger
from src.services.mqtt_services import fast_mqtt

# Entities
from src.entities.entity_utils import Entity


class Locker(Entity):
    """Add behaviour to a locker instance."""

    def __getattr__(self, name):
        """Delegate attribute access to the internal document"""
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the internal document, except for 'document' itself"""
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    def __init__(self, document: LockerModel = None):
        super().__init__()
        self.document = document

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
    async def find_available(cls, station: StationModel, locker_type: str):
        """Find an available locker at this station."""
        instance = cls()

        # 1. Find a stale sessions at this station
        stale_session = await SessionModel.find(
            SessionModel.assigned_station.id == station.id,  # pylint: disable=no-member
            SessionModel.assigned_locker.locker_type == locker_type,  # pylint: disable=no-member
            SessionModel.session_state == SessionStates.STALE
        ).first_or_none()

        if stale_session:
            instance.document = await LockerModel.get(stale_session.assigned_locker.id)
            return instance

        # 2. Find all active sessions at this station
        active_sessions = await SessionModel.find(
            SessionModel.assigned_station.id == station.id,
            SessionModel.is_active == True,
            fetch_links=True
        ).to_list()

        # 3: Find a locker at this station that matches the type and does not belong to such a session
        available_locker = await LockerModel.find(
            # TODO; FIXME cannot find locker with this
            # LockerModel.station.id == station.id,  # pylint: disable=no-member
            LockerModel.locker_type == locker_type,
            NotIn(LockerModel.id,  [
                session.assigned_locker.id for session in active_sessions])  # pylint: disable=no-member
        ).first_or_none()
        if available_locker:
            instance.document = available_locker

        return instance

    @property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.document is not None

    async def register_state(self, state: LockerStates):
        """Update the reported (actual) locker state"""
        await self.document.update(Set({LockerModel.reported_state: state}))

    async def set_state(self, state: LockerStates):
        """Send a message to the station to unlock the locker."""
        await self.document.fetch_link(LockerModel.station)
        fast_mqtt.publish(
            f'stations/{self.station.call_sign}/locker/{self.station_index}/instruct', state.value)
