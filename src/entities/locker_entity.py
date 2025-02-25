"""This module provides utilities for  database for lockers."""
# Beanie
from beanie.operators import NotIn, In, Or
from beanie import SortDirection
# Entities
from src.entities.entity_utils import Entity
from src.entities.station_entity import Station
# Models
from src.models.locker_models import (
    LockerModel,
    LockerState,
    LockerType)
from src.models.session_models import (
    SessionModel,
    SessionState,
    ReducedSessionView,
    ACTIVE_SESSION_STATES)
from src.models.task_models import (
    TaskItemModel,
    TaskTarget,
    TaskType,
    TaskState)
# Services
from src.services.logging_services import logger_service as logger
from src.services.mqtt_services import fast_mqtt
# Exceptions
from src.exceptions.locker_exceptions import LockerNotAvailableException


class Locker(Entity):
    """Add behaviour to a locker instance."""
    doc: LockerModel

    @classmethod
    async def find_available(cls, station: Station, locker_type: LockerType):
        """Find an available locker at this station."""
        instance = cls()

        # 1: Get all active session at this station
        active_sessions = await SessionModel.find(
            SessionModel.assigned_station.callsign == station.doc.callsign,  # pylint: disable=no-member
            Or(In(SessionModel.session_state, ACTIVE_SESSION_STATES),
                SessionModel.session_state == SessionState.STALE),
            fetch_links=True
        ).project(ReducedSessionView).sort(
            (SessionModel.created_at, SortDirection.ASCENDING)).to_list()
        occupied_locker_ids = [
            session.assigned_locker for session in active_sessions]

        # 2: Get all pending reservations for this station
        pending_reservations = await TaskItemModel.find(
            TaskItemModel.assigned_station.callsign == station.doc.callsign,  # pylint: disable=no-member
            TaskItemModel.target == TaskTarget.USER,
            TaskItemModel.task_type == TaskType.RESERVATION,
            TaskItemModel.task_state != TaskState.COMPLETED,
            fetch_links=True
        ).to_list()
        reserved_locker_ids = [
            reservation.assigned_locker.id for reservation in pending_reservations]

        # 3: Try to find a stale session whose assigned locker can be used
        stale_session = await SessionModel.find(
            SessionModel.assigned_station.callsign == station.doc.callsign,  # pylint: disable=no-member
            SessionModel.session_state == SessionState.STALE,
            fetch_links=True
        ).first_or_none()
        if stale_session:
            logger.debug(
                f"Found stale locker '#{stale_session.assigned_locker.id}'.")
            if stale_session.assigned_locker.id not in reserved_locker_ids + occupied_locker_ids:
                instance.doc = stale_session.assigned_locker
                return instance

        # 4: Find a locker that is still available
        available_locker = await LockerModel.find(
            LockerModel.station.id == station.doc.id,  # pylint: disable=no-member
            LockerModel.locker_type == locker_type.name,  # pylint: disable=no-member
            NotIn(LockerModel.id, reserved_locker_ids + occupied_locker_ids),
            fetch_links=True
        ).first_or_none()
        if available_locker:
            instance.doc = available_locker
            return instance

        raise LockerNotAvailableException(
            station_callsign=station.callsign,
            locker_type=locker_type)

    @property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.doc is not None

    async def register_state(self, state: LockerState):
        """Update the reported (actual) locker state"""
        logger.debug(
            (f"Locker '{self.doc.callsign}'/"
             f"'#{self.doc.id}' registered as: {state}."))
        self.doc.locker_state = state
        await self.doc.save_changes(skip_actions=['log_changes'])

    async def instruct_state(self, state: LockerState):
        """Send a message to the station to unlock the locker."""
        logger.debug(
            (f"Sending {state} instruction to locker '#{self.doc.id}' "
             f"at station '#{self.doc.station.callsign}'."))
        fast_mqtt.publish(
            f'stations/{self.doc.station.callsign}/locker/{self.doc.station_index}/instruct', state.value)
