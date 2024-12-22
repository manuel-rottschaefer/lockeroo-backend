"""Provides utility functions for the locker management backend."""
# Types
from typing import Dict
import yaml
# Beanie
from beanie import SortDirection
# Entities
from src.entities.task_entity import Task, restart_expiration_manager
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker, LockerStates
# Models
from src.models.session_models import SessionStates
from src.models.locker_models import LockerModel, LockerTypes
from src.models.task_models import TaskItemModel, TaskStates, TaskType, TaskTarget
from src.services.action_services import create_action
# Services
from src.services.logging_services import logger
# Exceptions
from src.exceptions.session_exceptions import SessionNotFoundException
from src.exceptions.task_exceptions import TaskNotFoundException
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


async def handle_unlock_confirmation(
        callsign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been unlocked"""
    # 1: Find the affected locker
    locker: Locker = Locker(await LockerModel.find(
        LockerModel.station.callsign == callsign,  # pylint: disable=no-member
        LockerModel.station_index == locker_index,  # pylint: disable=no-member
        fetch_links=True
    ).first_or_none())
    if not locker.exists:
        raise LockerNotFoundException(
            station=callsign,
            locker_index=locker_index)
    logger.info(
        (f"Station '{callsign}' reported {LockerStates.UNLOCKED} "
         f"at locker {locker_index} ('#{locker.id}')."))

    # 2: Find the affected, pending task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.LOCKER,
        TaskItemModel.task_type == TaskType.CONFIRMATION,
        TaskItemModel.task_state == TaskStates.PENDING,
        TaskItemModel.assigned_station.callsign == callsign,  # pylint: disable=no-member
        TaskItemModel.assigned_locker.id == locker.document.id,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_ts, SortDirection.DESCENDING
    )).first_or_none())
    if not task.exists:
        raise TaskNotFoundException(
            task_type=TaskType.CONFIRMATION,
            assigned_station=callsign,
            raise_http=False)

    # 3: Check if the reported locker matches that of the task
    await task.fetch_link(TaskItemModel.assigned_locker)
    assert (locker.callsign == task.assigned_locker.callsign
            ), f"Locker '{locker.id}' does not match task '{task.id}'."

    # 4: Check whether the locker was actually registered as unlocked
    if locker.reported_state != LockerStates.LOCKED.value:
        # TODO: This should maybe be an assert as it should never happen in prod
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

    # 8: Create a queue item for the user to lock the locker
    await Task().create(
        task_target=TaskTarget.LOCKER,
        task_type=TaskType.REPORT,
        session=session.document,
        station=locker.document.station,
        locker=locker.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.STALE],
    )


async def handle_lock_report(
        callsign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been closed"""
    # 1: Find the affected, pending task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.LOCKER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskStates.PENDING,
        TaskItemModel.assigned_station.callsign == callsign,  # pylint: disable=no-member
        TaskItemModel.assigned_locker.station_index == locker_index,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_ts, SortDirection.DESCENDING
    )).first_or_none())
    if not task.exists:
        raise TaskNotFoundException(
            task_type=TaskType.REPORT,
            assigned_station=callsign,
            raise_http=False)

    # 2: Get the affected locker
    locker: Locker = Locker(task.assigned_locker)
    assert locker.exists, f"Locker '{locker.id}' does not exist."
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
        task_target=TaskTarget.USER,
        task_type=TaskType.REPORT,
        session=session.document,
        station=locker.document.station,
        locker=locker.document,
        queued_state=next_state,
        timeout_states=[SessionStates.STALE],
    )
