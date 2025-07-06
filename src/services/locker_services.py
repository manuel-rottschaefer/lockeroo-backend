"""
Lockeroo.locker_services
-------------------------
This module provides locker management utilities and endpoint logic

Key Features:
    - Locker type import from configuration file at startup
    - Provides endpoint logic for station reports related to lockers

Dependencies:
    - beanie
"""
# Basics
from pathlib import Path
from typing import List, Optional
import yaml
# beanie
from beanie import SortDirection
from beanie.operators import In
# Entities
from src.entities.snapshot_entity import Snapshot
from src.entities.locker_entity import Locker, LockerState
from src.entities.session_entity import Session
from src.entities.task_entity import Task
from src.exceptions.locker_exceptions import (
    InvalidLockerReportException,
    InvalidLockerStateException)
# Models
from lockeroo_models.station_models import PaymentMethod
from lockeroo_models.locker_models import LockerType
from lockeroo_models.snapshot_models import SnapshotModel
from lockeroo_models.session_models import (
    SessionState,
    ACTIVE_SESSION_STATES)
from lockeroo_models.task_models import (
    TaskItemModel,
    TaskState,
    TaskTarget,
    TaskType)
# Services
from src.services.task_services import task_manager
from src.services.logging_services import logger_service as logger
# Exceptions
from src.exceptions.task_exceptions import TaskNotFoundException


def load_locker_types(config_path: str) -> Optional[List[LockerType]]:
    """Load locker types from configuration file."""
    locker_types: List[LockerType] = []
    try:
        with open(Path(__file__).parent / config_path, 'r', encoding='utf-8') as cfg:
            type_dicts = yaml.safe_load(cfg)
            locker_types.extend(LockerType(name=name, **details)
                                for name, details in type_dicts.items())
        return locker_types
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {config_path}.")
    except yaml.YAMLError as e:
        logger.warning(f"Error parsing YAML configuration: {e}")
    except TypeError as e:
        logger.warning(f"Data structure mismatch: {e}")


# Load locker types from configuration
locker_type_config = Path(__file__).resolve(
).parent.parent / "config/locker_types.yml"
LOCKER_TYPES: List[LockerType] = load_locker_types(
    config_path=locker_type_config
)
LOCKER_TYPE_NAMES = [locker.name for locker in LOCKER_TYPES]


async def handle_unlock_confirmation(
        locker_callsign: str,):
    """Process and verify a station report that a locker has been unlocked"""
    logger.info(
        (f"Locker '{locker_callsign}' reported {LockerState.UNLOCKED}'"))

    # 1: Find the affected, pending task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.LOCKER,
        TaskItemModel.task_type == TaskType.CONFIRMATION,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_locker.callsign == locker_callsign,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        raise TaskNotFoundException(
            task_type=TaskType.CONFIRMATION,
            raise_http=False)

    await task.doc.fetch_all_links()
    locker = Locker(task.assigned_locker)

    # 3: Check if the reported locker matches that of the task
    assert (locker.doc.callsign == task.doc.assigned_locker.callsign
            ), f"Locker '#{locker.id}' does not match task '#{task.doc.id}'."

    # 4: Check whether the locker is actually registered as unlocked
    assert (locker.doc.locker_state == LockerState.LOCKED
            ), f"Locker '#{locker.doc.id}' is not locked."

    # 5: Find the assigned session
    assert task.assigned_session, f"Task '#{task.id}' has no assigned session."
    session: Session = Session(task.assigned_session)

    # Verify session state for terminal payment sessions
    expected_states = [
        SessionState.VERIFICATION,
        SessionState.PAYMENT,
        SessionState.ACTIVE]
    assert (session.doc.session_state in expected_states), (
        f"Session '#{session.id}' is in {session.session_state}, expected "
        f"{expected_states}.")

    # 6: If those checks pass, register locker state and complete task
    await locker.register_state(LockerState.UNLOCKED)
    await task.complete(task_manager=task_manager)

    # 8: Create a queue item for the user to lock the locker
    # TODO: FIXME this is not an optimal solution
    next_state = session.next_state if session.doc.session_state in [
        SessionState.VERIFICATION,
        SessionState.PAYMENT
    ] else SessionState.HOLD

    if next_state == SessionState.HOLD and session.doc.payment_method != PaymentMethod.TERMINAL:
        # Also create a task that allows the user to start the
        # payment process without closing the locker
        task = await Task(TaskItemModel(
            target=TaskTarget.USER,
            task_type=TaskType.REPORT,
            assigned_user=session.doc.assigned_user,
            assigned_session=session.doc,
            assigned_station=locker.doc.station,
            assigned_locker=locker.doc,
            timeout_states=[SessionState.EXPIRED],
        )).insert()

    task = await Task(TaskItemModel(
        target=TaskTarget.LOCKER,
        task_type=TaskType.REPORT,
        queued_state=next_state,
        assigned_user=session.doc.assigned_user,
        assigned_session=session.doc,
        assigned_station=locker.doc.station,
        assigned_locker=locker.doc,
        timeout_states=[SessionState.EXPIRED],
    )).insert()
    await task.evaluate_queue(task_manager=task_manager)


async def handle_lock_report(locker_callsign: str,):
    """Process and verify a station report that a locker has been closed"""
    logger.info(
        (f"Locker '{locker_callsign}' reported {LockerState.LOCKED}"))

    # 1: Find the affected, pending task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.LOCKER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES + [SessionState.CANCELED]),
        TaskItemModel.assigned_locker.callsign == locker_callsign,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        # TODO: Improve error handling here
        raise TaskNotFoundException(
            task_type=TaskType.REPORT,
            raise_http=False)

    # 2: Get the affected locker
    locker: Locker = Locker(task.assigned_locker)
    assert locker.exists, f"Locker '#{locker.id}' does not exist."

    # 3: Check if the reported locker matches that of the task
    await task.doc.fetch_link(TaskItemModel.assigned_locker)
    if locker.callsign != task.assigned_locker.callsign:
        raise InvalidLockerReportException(
            locker_id=locker.id, raise_http=False)

    # 4: Check whether the locker was actually registered as unlocked
    if locker.doc.locker_state not in [LockerState.UNLOCKED, LockerState.STALE]:
        raise InvalidLockerStateException(
            locker_id=locker.id,
            expected_state=LockerState.UNLOCKED,
            actual_state=locker.doc.locker_state,
            raise_http=False)

    # 5: Find the assigned session
    assert task.assigned_session, f"Task '#{task.id}' has no assigned session."
    session: Session = Session(task.assigned_session)

    accepted_states = [
        SessionState.HOLD,
        SessionState.STASHING,
        SessionState.RETRIEVAL,
        SessionState.CANCELED]
    assert (session.doc.session_state in accepted_states
            ), (f"Session '#{session.id}' is in {session.session_state}"
                f", expected {accepted_states}.")

    # 6: If those checks pass, register locker state and complete task
    await locker.register_state(LockerState.LOCKED)
    await task.complete(task_manager=task_manager)

    # 7: If the session is on hold, find the user task and complete it
    if session.doc.session_state == SessionState.HOLD:
        user_task: Task = Task(await TaskItemModel.find(
            TaskItemModel.target == TaskTarget.USER,
            TaskItemModel.task_type == TaskType.REPORT,
            TaskItemModel.task_state == TaskState.PENDING,
            TaskItemModel.assigned_session.id == session.doc.id,  # pylint: disable=no-member
            fetch_links=True
        ).first_or_none())
        if user_task.exists:
            logger.debug(
                f"Also completing user report task '{user_task.id}'.", session_id=session.id)
            await user_task.complete(task_manager=task_manager)

    # 7: Catch completed sessions
    if session.next_state == SessionState.COMPLETED:
        return await session.handle_conclude(SessionState.COMPLETED)

    # 8: Catch canceled sessions
    if session.doc.session_state == SessionState.CANCELED:
        return

    # 9: Await user to return to the locker to pick up his stuff.
    task = await Task(TaskItemModel(
        task_type=TaskType.REPORT,
        target=TaskTarget.USER,
        assigned_user=session.doc.assigned_user,
        assigned_session=session.doc,
        assigned_station=locker.doc.station,
        assigned_locker=locker.doc,
        timeout_states=[SessionState.ABANDONED],
        queued_state=session.next_state
    )).insert()
    await task.activate(task_manager=task_manager)
