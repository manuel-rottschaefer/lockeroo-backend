"""Provides utility functions for the locker management backend."""
# Types
from typing import Dict
import yaml

# Beanie
from beanie import SortDirection
# Entities
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker
from src.entities.task_entity import Task, restart_expiration_manager
# Models
from src.models.locker_models import LockerStates, LockerTypes
from src.models.session_models import SessionStates
from src.models.task_models import TaskItemModel, TaskStates, TaskTypes
from src.services.action_services import create_action
# Services
from src.services.logging_services import logger
from src.exceptions.session_exceptions import SessionNotFoundException
from src.exceptions.task_exceptions import TaskNotFoundException
# Exceptions
from src.exceptions.locker_exceptions import (
    LockerNotFoundException,
    InvalidLockerStateException,
    InvalidLockerReportException)

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


async def handle_unlock_report(
        callsign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been unlocked"""
    # 1: Find the affected locker
    locker: Locker = await Locker().find(
        station_callsign=callsign,
        index=locker_index)
    if not locker.exists:
        raise LockerNotFoundException(
            station=callsign,
            locker_index=locker_index)
    logger.info(
        (f"Station '{callsign}' reported {LockerStates.UNLOCKED} "
         f"at locker {locker_index} ('#{locker.id}')."))

    # 2: Find the affected, pending task
    task: Task = await Task().find(
        task_type=TaskTypes.CONFIRMATION,
        task_state=TaskStates.PENDING,
        assigned_locker=locker.document.id)
    if not task.exists:
        raise TaskNotFoundException(
            task_type=TaskTypes.CONFIRMATION,
            assigned_station=callsign,
            raise_http=False)

    # 3: Check if the reported locker matches that of the task
    await task.fetch_link(TaskItemModel.assigned_locker)
    if locker.callsign != task.assigned_locker.callsign:
        raise InvalidLockerReportException(
            locker_id=locker.id, raise_http=False)

    # 4: Check whether the locker was actually registered as unlocked
    if locker.reported_state != LockerStates.LOCKED.value:
        raise InvalidLockerStateException(
            locker_id=locker.id,
            expected_state=LockerStates.LOCKED,
            actual_state=locker.reported_state,
            raise_http=False)

    # 5: Find the assigned session
    session: Session = Session(task.assigned_session)
    if not session.exists:
        raise SessionNotFoundException(
            session_id=task.assigned_session.id,
            raise_http=False)

    assert (session.document.session_state in [
        SessionStates.VERIFICATION,
        SessionStates.PAYMENT,
        SessionStates.HOLD]
    ), f"Session '{session.id}' is in an invalid state."

    # 6: If those checks pass, update the locker and create an action
    await locker.register_state(LockerStates.UNLOCKED)
    await create_action(session.id, session.session_state)

    # 7: Complete the task and restart the expiration manager
    await task.complete()
    await restart_expiration_manager()

    # 8: Create a queue item for the user
    await Task().create(
        task_type=TaskTypes.LOCKER,
        session=session.document,
        station=locker.document.station,
        locker=locker.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.STALE],
        has_queue=False
    )


async def handle_lock_report(
        callsign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been closed"""
    # 1: Find the affected, pending task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.task_type == TaskTypes.LOCKER,
        TaskItemModel.task_state == TaskStates.PENDING,
        TaskItemModel.assigned_station.callsign == callsign,  # pylint: disable=no-member
        TaskItemModel.assigned_locker.station_index == locker_index,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_ts, SortDirection.DESCENDING
    )).first_or_none())
    if not task.exists:
        raise TaskNotFoundException(
            task_type=TaskTypes.LOCKER,
            assigned_station=callsign,
            raise_http=False)

    # 2: Get the affected locker
    locker: Locker = Locker(task.assigned_locker)
    logger.info(
        (f"Station '{callsign}' reported {LockerStates.LOCKED} "
         f"at locker {locker_index} ('#{locker.id}')."))

    # 3: Check if the reported locker matches that of the task
    await task.fetch_link(TaskItemModel.assigned_locker)
    if locker.callsign != task.assigned_locker.callsign:
        raise InvalidLockerReportException(
            locker_id=locker.id, raise_http=False)

    # 4: Check whether the locker was actually registered as unlocked
    if locker.reported_state != LockerStates.UNLOCKED.value:
        raise InvalidLockerStateException(
            locker_id=locker.id,
            expected_state=LockerStates.UNLOCKED,
            actual_state=locker.reported_state,
            raise_http=False)

    # 5: Find the assigned session
    session: Session = Session(task.assigned_session)
    if not session.exists:
        raise SessionNotFoundException(
            session_id=task.assigned_session.id,
            raise_http=False)

    assert (session.document.session_state in [
        SessionStates.STASHING,
        SessionStates.ACTIVE,
        SessionStates.RETRIEVAL]
    ), f"Session '{session.id}' is in an invalid state."

    # 6: If those checks pass, update the locker and create an action
    await locker.register_state(LockerStates.LOCKED)
    await create_action(session.id, session.session_state)

    # 7: Complete the task and restart the expiration manager
    await task.complete()
    await restart_expiration_manager()

    # 8: Catch completed sessions
    next_state: SessionStates = await session.next_state
    if next_state == SessionStates.COMPLETED:
        return await session.handle_conclude()

    # 9: Await user to return to the locker to pick up his stuff.
    await Task().create(
        task_type=TaskTypes.LOCKER,
        session=session.document,
        station=locker.document.station,
        locker=locker.document,
        queued_state=next_state,
        timeout_states=[SessionStates.STALE],
        has_queue=False
    )
