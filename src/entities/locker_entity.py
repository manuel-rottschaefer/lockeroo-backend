"""
Lockeroo.locker_entity
-------------------------
This module provides the Locker Entity class

Key Features:
    - Provides a functionality wrapper for Beanie Locker Documents

Dependencies:
    - beanie
"""
# Basics
from typing import Optional
# Beanie
from beanie.operators import NotIn, In, Or
from beanie import SortDirection
# Entities
from src.entities.entity import Entity
from src.entities.station_entity import Station
# Models
from lockeroo_models.locker_models import (
    LockerModel,
    LockerState,
    LockerType)
from lockeroo_models.session_models import (
    SessionModel,
    SessionState,
    ACTIVE_SESSION_STATES)
from lockeroo_models.task_models import (
    TaskItemModel,
    TaskTarget,
    TaskType,
    TaskState)
# Services
from src.services.logging_services import logger_service as logger
from src.services.mqtt_services import fast_mqtt


class Locker(Entity):
    """
    Lockeroo.Locker
    -------
    A class representing a locker at a station.
    Lockers store the belongings of the user and can be opened and closed by them.

    Key Features:
    - `__init__`: Initializes a locker object and adds event logic to it
    - '_add_handlers': Adds event logic to a locker object
    - 'find_available': Finds a suitable locker in the database, given requirements 
    - 'register_state': Registers a notified state of a locker at a station
    - 'instruct_state': Sends an instruction to a locker
    """
    doc: LockerModel

    def __init__(self, document=None):
        super().__init__(document)
        self._add_handlers()

    def _add_handlers(self):
        def log_changes_model_handler(locker: LockerModel):
            """Log the Database operation for debugging purposes."""
            logger.debug(
                (f"Locker '#{locker.callsign}' has been registered "
                    f"as {locker.locker_state}."))

        LockerModel.log_state = log_changes_model_handler

    @classmethod
    async def find_available(cls, station: Station, locker_type: LockerType):
        """Finds a suitable locker in the database, given the requirements
        for stations and locker_types.

        Args:
            - self Locker: The locker Entity
            - station[Station]: The station to which the locker must belong
            - locker_type[LockerType]: The type to which the locker must belong

        Returns:
            Locker: The retrieved locker, if one exists

        Raises:
            -

        Example:
            >>> locker.find_available()
            Locker
        """
        instance = cls()

        # 1: Get all active and stale sessions at this station
        sessions = await SessionModel.find(
            SessionModel.assigned_station.callsign == station.doc.callsign,
            Or(In(SessionModel.session_state, ACTIVE_SESSION_STATES),
                SessionModel.session_state == SessionState.STALE),
            fetch_links=True
        ).sort(
            (SessionModel.created_at, SortDirection.ASCENDING)
        ).to_list()

        # Separate session locker IDs by state
        stale_locker_ids = []
        occupied_locker_ids = []

        for session in sessions:
            if session.session_state == SessionState.STALE:
                stale_locker_ids.append(session.assigned_locker.id)
            else:
                occupied_locker_ids.append(session.assigned_locker.id)

        # 2: Get all reserved lockers (pending reservations)
        pending_reservations = await TaskItemModel.find(
            TaskItemModel.assigned_station.callsign == station.doc.callsign,
            TaskItemModel.target == TaskTarget.USER,
            TaskItemModel.task_type == TaskType.RESERVATION,
            TaskItemModel.task_state != TaskState.COMPLETED,
            fetch_links=True
        ).to_list()

        reserved_locker_ids = [
            reservation.assigned_locker.id for reservation in pending_reservations
        ]

        # 3: Try to reuse a stale-session locker if it's not reserved
        for locker_id in stale_locker_ids:
            if locker_id not in reserved_locker_ids:
                locker = await LockerModel.get(locker_id, fetch_links=True)
                if locker and locker.locker_type == locker_type.name:
                    instance.doc = locker
                    return instance

        # 4: Otherwise, find any unoccupied and unreserved locker
        unavailable_ids = set(reserved_locker_ids + occupied_locker_ids)

        print(station.doc.full_name, locker_type.name)

        available_locker = await LockerModel.find(
            LockerModel.station.id == station.doc.id,
            LockerModel.locker_type == locker_type.name,
            NotIn(LockerModel.id, list(unavailable_ids)),
            fetch_links=True
        ).first_or_none()

        if available_locker:
            instance.doc = available_locker
        return instance

    async def register_state(self, state: LockerState):
        """Stores a locker state upon notification by the station and logs this

        Args:
            - self[Locker]: The locker Entity
            - state[LockerState]: the notified locker state

        Returns:
            None

        Raises:
            -

        Example:
            >>> locker.register_state()
            None
        """
        logger.debug(
            (f"Locker '{self.doc.callsign}'/"
             f"'#{self.doc.id}' registered as: {state}."))
        self.doc.locker_state = state
        await self.doc.save_changes()

    async def instruct_state(self, state: LockerState, task: TaskItemModel):
        """Sends an instruction to a locker at a station

        Args:
            - self [Locker]: The locker Entity
            - state [LockerState]: the new locker state that it should take on
            - task_id [str]: The ID of the belonging task

        Returns:
            None

        Raises:
            -

        Example:
            >>> locker.instruct_state()
            None
        """
        logger.debug(
            (f"Sending {state} instruction to locker '{self.doc.callsign}' "
             f"for task '#{task.id}'."), session_id=task.assigned_session.id)
        fast_mqtt.publish(
            f'lockers/{self.doc.callsign}/instruct', state.value)
