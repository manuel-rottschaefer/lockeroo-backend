"""Provides utility functions for the locker management backend."""

# Basics
# Typing
from typing import Dict

import yaml
from beanie import PydanticObjectId as ObjId

# Entities
from src.entities.station_entity import Station
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker
from src.entities.task_entity import Task, restart_expiration_manager
# Models
from src.models.locker_models import LockerModel, LockerStates, LockerTypes
from src.models.session_models import SessionStates
from src.models.task_models import TaskItemModel, TaskStates, TaskTypes
from src.services.action_services import create_action
# Services
from src.services.logging_services import logger
from src.exceptions.station_exceptions import StationNotFoundException
from src.exceptions.session_exceptions import (
    SessionNotFoundException, InvalidSessionStateException)
from src.exceptions.task_exceptions import TaskNotFoundException

# Singleton for pricing models
LOCKER_TYPES: Dict[str, LockerTypes] = None

CONFIG_PATH = 'src/config/locker_types.yml'

if LOCKER_TYPES is None:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as cfg:
            type_dicts = yaml.safe_load(cfg)
            LOCKER_TYPES = {name: LockerTypes(name=name, **details)
                            for name, details in type_dicts.items()}
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {CONFIG_PATH}.")
        LOCKER_TYPES = {}
    except yaml.YAMLError as e:
        logger.warning(f"Error parsing YAML configuration: {e}")
        LOCKER_TYPES = {}
    except TypeError as e:
        logger.warning(f"Data structure mismatch: {e}")
        LOCKER_TYPES = {}


class LockerNotFoundException(Exception):
    """Exception raised when a locker cannot be found by a given query."""

    def __init__(self, locker_id: ObjId = None, ):
        super().__init__()
        self.locker = locker_id
        logger.warning(
            f"Could not find locker '{self.locker}' in database.")

    def __str__(self):
        return f"Locker '{self.locker}' not found.)"


class InvalidLockerStateException(Exception):
    """Exception raised when a locker is not matching the expected state."""

    def __init__(self, locker_id: ObjId, expected_state: LockerStates, actual_state: LockerStates):
        super().__init__()
        self.locker_id = locker_id
        self.expected_state = expected_state
        self.actual_state = actual_state
        logger.warning(
            f"Locker '{locker_id}' should be in {
                expected_state}, but is currently registered as {actual_state}")

    def __str__(self):
        return f"Invalid state of locker '{self.locker_id}'.)"


async def handle_lock_report(callsign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been closed"""
    # 1: Find the affected locker
    locker: Locker = await Locker().find(
        station_callsign=callsign,
        index=locker_index)
    if not locker.exists:
        raise LockerNotFoundException(locker_id=None)

    # 2: Find the affected task
    task: Task = await Task().find(
        task_type=TaskTypes.LOCKER,
        task_state=TaskStates.PENDING,
        assigned_locker=locker.document.id)
    if not task.exists:
        logger.warning(f"Cannot find task of {
            TaskTypes.LOCKER} at station '{callsign}'.")
        return
    await task.fetch_all_links()

    # 3: Find the affected locker
    assigned_locker: LockerModel = task.assigned_session.assigned_locker
    locker: Locker = Locker(assigned_locker)
    if not locker.exists:
        raise LockerNotFoundException(locker_id=assigned_locker.id)

    logger.info(f"Station '{callsign}' reports locker '{
                locker.callsign}' as {LockerStates.LOCKED}.")

    # 4: Check that the locker matches
    if locker.station_index != locker_index:
        logger.debug("Invalid message")
        return

    if locker.reported_state != LockerStates.UNLOCKED.value:
        logger.error(f"Locker '{locker.id}' should be unlocked, but is {
                     locker.reported_state}.")
        return

    # 5: Find the station to get its ID
    station: Station = Station(locker.station)
    if not station.exists:
        raise StationNotFoundException(callsign=callsign)

    # 6: Find the assigned session
    session: Session = Session(task.assigned_session)
    if not session.exists:
        raise SessionNotFoundException(session_id=task.assigned_session.id)

    # 7: If those checks pass, update the locker and create an action
    await locker.register_state(LockerStates.LOCKED)
    await session.document.save_changes()
    await create_action(session.id, session.session_state)

    # 8: Complete the task and restart the expiration manager
    await task.complete()
    await restart_expiration_manager()

    # 9: Catch a completed session here
    next_state: SessionStates = await session.next_state
    if next_state == SessionStates.COMPLETED:
        return await session.handle_conclude()

    # 10: Await user to return to the locker to pick up his stuff.
    await Task().create(
        task_type=TaskTypes.LOCKER,
        session=session.document,
        station=station.document,
        locker=locker.document,
        queued_state=next_state,
        timeout_states=[SessionStates.STALE],
        has_queue=False
    )


async def handle_unlock_confirmation(
        callsign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been unlocked"""
    # 1: Find the affected locker
    locker: Locker = await Locker().find(
        station_callsign=callsign, index=locker_index)
    if not locker.exists:
        # TODO: Improve this exception
        raise LockerNotFoundException(locker_id=None)

    # 2: Look for a task that is pending at this locker
    task: Task = await Task().find(
        task_type=TaskTypes.CONFIRMATION,
        task_state=TaskStates.PENDING,
        assigned_locker=locker.document.id)
    if not task.exists:
        # TODO: Create a custom exception for this.
        raise TaskNotFoundException(
            task_type=TaskTypes.CONFIRMATION, assigned_station=callsign)

    await task.fetch_link(TaskItemModel.assigned_session)
    locker: Locker = Locker(task.assigned_session.assigned_locker)
    if not locker.exists:
        raise LockerNotFoundException(
            locker_id=task.assigned_session.assigned_locker.id)
    logger.info(f"Station '{callsign}' reports locker '{
                locker.callsign}' as {LockerStates.UNLOCKED}.")

    # 2: Check whether the internal locker state matches the reported situation
    if locker.reported_state != LockerStates.LOCKED.value:
        logger.error(f"Locker '{locker.callsign}' should be locked, but is {
                     locker.reported_state}.")
        return

    station: Station = await Station().find(callsign=callsign)
    if not station.exists:
        raise StationNotFoundException(callsign=callsign)

    # 4: Find the assigned session
    accepted_session_states = [SessionStates.VERIFICATION,
                               SessionStates.PAYMENT,
                               SessionStates.HOLD]
    session: Session = Session(task.assigned_session)
    if not session.exists:
        raise SessionNotFoundException(session_id=task.assigned_session.id)

    if session.session_state not in accepted_session_states:
        raise InvalidSessionStateException(
            session_id=session.id,
            expected_states=accepted_session_states,
            actual_state=session.session_state
        )

    # 5: Update locker and session states
    locker.document.reported_state = LockerStates.UNLOCKED
    await locker.document.save_changes()

    await task.complete()
    await restart_expiration_manager()

    # 7: Create a queue item for the user
    await Task().create(
        task_type=TaskTypes.LOCKER,
        session=session.document,
        station=station.document,
        locker=locker.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.STALE],
        has_queue=False
    )

    # 8: Create action entry
    await create_action(session.id, session.session_state)
