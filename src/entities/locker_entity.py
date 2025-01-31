"""This module provides utilities for  database for lockers."""
# Basics
from typing import List
# Entities
from src.entities.entity_utils import Entity
from src.entities.station_entity import Station
# Models
from src.models.locker_models import (
    LockerModel,
    LockerState,
    LockerType,
    ReducedLockerView)
from src.models.task_models import (
    TaskItemModel,
    TaskTarget,
    TaskType,
    TaskState)
# Services
from src.services.logging_services import logger_service as logger
from src.services.mqtt_services import fast_mqtt


class Locker(Entity):
    """Add behaviour to a locker instance."""
    doc: LockerModel

    @classmethod
    async def find_available(cls, station: Station, locker_type: LockerType):
        """Find an available locker at this station."""
        instance = cls()

        # 1: Find all available lockers at the station
        available_lockers: List[ReducedLockerView] = await station.get_available_lockers()

        # 2: Get all pending reservations for this station
        pending_reservations = await TaskItemModel.find(
            TaskItemModel.target == TaskTarget.USER,
            TaskItemModel.task_type == TaskType.RESERVATION,
            TaskItemModel.task_state == TaskState.PENDING,
            TaskItemModel.assigned_station.id == station.doc.id,  # pylint: disable=no-member
            fetch_links=True
        ).to_list()

        # 3: Check if there are any stale lockers, if so return the first one
        for locker in available_lockers:
            if locker.locker_state == LockerState.STALE:
                instance.doc = await LockerModel.get(locker.id)
                return instance

        # 4: Go through the list of lockers and find one that is locked and not reserved
        for locker in available_lockers:
            # TODO: Locker type filtering is not quite clear.
            if locker.locker_state == LockerState.LOCKED:
                if locker.id not in [
                        reservation.assigned_locker.id for reservation in pending_reservations]:
                    instance.doc = await LockerModel.get(locker.id)
                    return instance

        logger.debug((
            f"No available locker of type '{locker_type.name}' found "
            f"at station '{station.callsign}'."))

        return instance

    @property
    def exists(self) -> bool:
        """Check whether this object exists."""
        return self.doc is not None

    async def register_state(self, state: LockerState):
        """Update the reported (actual) locker state"""
        logger.debug(
            (f"Locker '{self.doc.callsign}'/"
             f"'#{self.doc.id}') registered as: {state}."))
        self.doc.locker_state = state
        await self.doc.save_changes(skip_actions=['log_changes'])

    async def instruct_state(self, state: LockerState):
        """Send a message to the station to unlock the locker."""
        logger.debug(
            (f"Sending {state} instruction to locker '#{self.doc.id}' "
             f"at station '#{self.doc.station.callsign}'."))
        fast_mqtt.publish(
            f'stations/{self.station.callsign}/locker/{self.station_index}/instruct', state.value)
