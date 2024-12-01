"""Provides utility functions for the locker management backend."""

# Basics
import yaml

# Typing
from typing import Dict
from enum import Enum

# Entities
from src.entities.station_entity import Station
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker
from src.entities.task_entity import Task

# Models
from src.models.locker_models import LockerType, LockerStates
from src.models.session_models import SessionStates
from src.models.task_models import TaskStates, TaskTypes

# Services
from src.services.logging_services import logger
from src.services.exceptions import ServiceExceptions
from src.services.action_services import create_action

# Singleton for pricing models
LOCKER_TYPES: Dict[str, LockerType] = None

CONFIG_PATH = 'src/config/locker_types.yml'

if LOCKER_TYPES is None:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as cfg:
            type_dicts = yaml.safe_load(cfg)
            LOCKER_TYPES = {name: LockerType(name=name, **details)
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


async def handle_lock_report(call_sign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been closed"""
    # 1: Find the affected task
    task: Task = await Task().find(
        call_sign=call_sign,
        task_type=TaskTypes.USER,
        task_state=TaskStates.PENDING,
        locker_index=locker_index)
    await task.fetch_links()

    # 2: Find the affected locker
    locker: Locker = Locker(task.assigned_session.assigned_locker)
    await locker.fetch_links()
    if not locker.exists:
        logger.info(ServiceExceptions.LOCKER_NOT_FOUND,
                    station=call_sign, detail=locker_index)

    # 3: Check that the locker matches
    if locker.station_index != locker_index:
        logger.debug("Invalid message")
        return

    if locker.reported_state != LockerStates.UNLOCKED.value:
        logger.error(f"Locker '{locker.id}' should be unlocked, but is {
                     locker.reported_state}.")
        return

    # 4: Find the station to get its ID
    station: Station = Station(locker.station)
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND,
                    station=call_sign)

    # 5: Find the assigned session
    session: Session = Session(task.assigned_session)
    if not session:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND, locker=locker.id)
        return

    # 6: If those checks pass, update the locker and create an action
    await locker.register_state(LockerStates.LOCKED)
    await create_action(session.id, session.session_state)

    # 6: Complete the previous task item
    await task.set_state(TaskStates.COMPLETED)

    # 7: Catch a completed session here
    next_state: SessionStates = await session.next_state
    if next_state == SessionStates.COMPLETED:
        await session.set_state(SessionStates.COMPLETED)
        await create_action(session_id=session.id,
                            action_type=SessionStates.COMPLETED)
        await session.handle_conclude()
        return

    # 8: Await user to return to the locker to pick up his stuff.
    await Task().create(
        task_type=TaskTypes.USER,
        station=station.document,
        session=session.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.STALE],
        has_queue=False
    )


async def handle_unlock_confirmation(
        call_sign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been unlocked"""
    # 1: Look for a task that is pending
    task: Task = await Task().find(call_sign=call_sign,
                                   task_type=TaskTypes.LOCKER,
                                   task_state=TaskStates.PENDING)
    await task.fetch_links()

    locker: Locker = Locker(task.assigned_session.assigned_locker)
    if not locker.exists:
        logger.info(ServiceExceptions.LOCKER_NOT_FOUND,
                    station=call_sign, detail=locker_index)

    # 2: Check whether the internal locker state matches the reported situation
    if locker.reported_state != LockerStates.LOCKED.value:
        logger.error(f"Locker '{locker.id}' should be locked, but is {
                     locker.reported_state}.")
        return

    station: Station = Station(task.assigned_station)
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND,
                    station=call_sign)

    # 4: Find the assigned session
    accepted_session_states = [SessionStates.VERIFICATION,
                               SessionStates.PAYMENT,
                               SessionStates.HOLD]
    session: Session = Session(task.assigned_session)
    if not session.exists:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND,
                    station=call_sign)
        return

    if session.session_state not in accepted_session_states:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session.id, detail=session.session_state)
        return

    # 5: Update locker and session states
    await locker.register_state(LockerStates.UNLOCKED)
    await task.set_state(TaskStates.COMPLETED)

    # 7: Create a queue item for the user
    await Task().create(
        task_type=TaskTypes.USER,
        station=station.document,
        session=session.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.STALE],
        has_queue=False
    )

    # 8: Create action entry
    await create_action(session.id, session.session_state)
