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
# Services
from src.services.logging_services import logger
from src.services.mqtt_services import fast_mqtt


class Locker(Entity):
    """Add behaviour to a locker instance."""
    doc: LockerModel

    @classmethod
    async def find_available(cls, station: Station, locker_type: LockerType):
        """Find an available locker at this station."""
        instance = cls()

        # 1. Find all active sessions at this station
        available_lockers: List[ReducedLockerView] = await station.get_available_lockers()

        # 2. Check if there are any stale lockers, if so return the first one
        for locker in available_lockers:
            if locker.locker_state == LockerState.STALE:
                instance.doc = await LockerModel.get(locker.id)
                return instance

        # 3. Check if there are any available lockers of the requested type
        if available_lockers[0] is not None:
            assert (available_lockers[0].locker_state == LockerState.LOCKED
                    ), f"Locker '#{available_lockers[0].id}' is not locked."
            instance.doc = available_lockers[0]

        assert (instance.exists
                ), f"No available lockers of type '{locker_type}' at station '{station.callsign}'."

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
