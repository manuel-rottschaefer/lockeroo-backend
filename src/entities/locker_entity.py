"""This module provides utilities for  database for lockers."""
# Beanie
from beanie import SortDirection
from beanie.operators import In, NotIn

# Entities
from src.entities.entity_utils import Entity
from src.models.locker_models import LockerModel, LockerState, LockerType
from src.models.session_models import (
    ACTIVE_SESSION_STATES,
    SessionModel,
    SessionState)
# Models
from src.models.station_models import StationModel
# Services
from src.services.logging_services import logger
from src.services.mqtt_services import fast_mqtt


class Locker(Entity):
    """Add behaviour to a locker instance."""
    doc: LockerModel

    @classmethod
    async def find_available(cls, station: StationModel, locker_type: LockerType):
        """Find an available locker at this station."""
        instance = cls()

        # 1. Find a stale session at this station
        stale_session = await SessionModel.find(
            SessionModel.assigned_station.id == station.id,  # pylint: disable=no-member
            SessionModel.assigned_locker.locker_type == locker_type.name,  # pylint: disable=no-member
            SessionModel.session_state == SessionState.STALE,
            fetch_links=True
        ).sort((SessionModel.created_at, SortDirection.ASCENDING)).first_or_none()

        if stale_session:
            instance.doc = await LockerModel.get(stale_session.assigned_locker.id)
            return instance

        # 2. Find all active sessions at this station
        active_sessions = await SessionModel.find(
            SessionModel.assigned_station.id == station.id,  # pylint: disable=no-member
            In(SessionModel.session_state, ACTIVE_SESSION_STATES),
            fetch_links=True
        ).sort((SessionModel.created_at, SortDirection.ASCENDING)).to_list()
        active_lockers = [
            session.assigned_locker.id for session in active_sessions]
        assert (station.locker_layout.locker_count < 30
                ), "Found more active lockers than exist at station."

        # 3: Find a locker at this station that matches the type and does not belong to such a session
        available_locker: LockerModel = await LockerModel.find(
            # LockerModel.station.id == station.id,  # pylint: disable=no-member
            LockerModel.locker_type.name == locker_type.name,
            NotIn(LockerModel.id,  active_lockers),
            fetch_links=True
        ).sort((LockerModel.total_session_count, SortDirection.ASCENDING)).first_or_none()
        if available_locker:
            instance.doc = available_locker

        return instance

    @property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.doc is not None

    async def register_state(self, state: LockerState):
        """Update the reported (actual) locker state"""
        logger.debug(f"Locker '#{self.doc.callsign.replace('#', '')}' ('{
                     self.doc.id}') registered as: {state}.")
        self.doc.reported_state = state
        await self.doc.save_changes(skip_actions=['log_changes'])

    async def instruct_state(self, state: LockerState):
        """Send a message to the station to unlock the locker."""
        logger.debug(
            (f"Sending {state} instruction to locker '#{self.doc.id}' "
             f"at station '#{self.doc.station.callsign}'."))
        fast_mqtt.publish(
            f'stations/{self.station.callsign}/locker/{self.station_index}/instruct', state.value)
