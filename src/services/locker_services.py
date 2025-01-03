"""Provides utility functions for the locker management backend."""
# Basics
from datetime import datetime
# Beanie
from beanie import SortDirection
from beanie.operators import In
# Entities
from src.entities.locker_entity import Locker, LockerState
from src.entities.session_entity import Session
from src.entities.task_entity import Task
from src.exceptions.locker_exceptions import (
    InvalidLockerReportException,
    InvalidLockerStateException)
# Exceptions
from src.exceptions.task_exceptions import TaskNotFoundException
from src.models.action_models import ActionModel, ActionType
from src.models.session_models import SessionModel
# Models
from src.models.session_models import SessionState
from src.models.task_models import (
    TaskItemModel,
    TaskState,
    TaskTarget,
    TaskType)
# Services
from src.services.logging_services import logger


async def handle_unlock_confirmation(
        callsign: str, station_index: int) -> None:
    """Process and verify a station report that a locker has been unlocked"""
    logger.info(
        (f"Station '{callsign}' reported {LockerState.UNLOCKED} "
         f"at locker {station_index}"))

    # 1: Find the affected, pending task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.LOCKER,
        TaskItemModel.task_type == TaskType.CONFIRMATION,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_station.callsign == callsign,  # pylint: disable=no-member
        TaskItemModel.assigned_locker.station_index == station_index,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        raise TaskNotFoundException(
            task_type=TaskType.CONFIRMATION,
            assigned_station=callsign,
            raise_http=False)

    # 2: Fetch the locker
    await task.doc.fetch_link(TaskItemModel.assigned_locker)
    locker: Locker = Locker(task.assigned_locker)

    # 3: Check if the reported locker matches that of the task
    await task.doc.fetch_link(TaskItemModel.assigned_locker)
    assert (locker.callsign == task.assigned_locker.callsign
            ), f"Locker '#{locker.id}' does not match task '#{task.id}'."

    # 4: Check whether the locker is actually registered as unlocked
    assert (locker.doc.reported_state == LockerState.LOCKED
            ), f"Locker '#{locker.doc.id}' is not locked."

    # 5: Find the assigned session
    assert task.assigned_session, f"Task '#{task.id}' has no assigned session."
    session: Session = Session(task.assigned_session)

    expected_states = [
        SessionState.VERIFICATION,
        SessionState.PAYMENT,
        SessionState.HOLD]
    assert (session.doc.session_state in expected_states
            ), (f"Session '#{session.id}' is in {session.session_state}, expected "
                f"{expected_states}.")

    # 6: If those checks pass, update the locker and create an action
    await locker.register_state(LockerState.UNLOCKED)

    # 7: Complete the task and restart the expiration manager
    await task.complete()

    # 8: Create a queue item for the user to lock the locker
    await Task(await TaskItemModel(
        target=TaskTarget.LOCKER,
        task_type=TaskType.REPORT,
        assigned_session=session.doc,
        assigned_station=locker.doc.station,
        assigned_locker=locker.doc,
        timeout_states=[SessionState.STALE],
        moves_session=True,
    ).insert()).activate()


async def handle_lock_report(
        callsign: str, station_index: int) -> None:
    """Process and verify a station report that a locker has been closed"""
    # 1: Find the affected, pending task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.LOCKER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_station.callsign == callsign,  # pylint: disable=no-member
        TaskItemModel.assigned_locker.station_index == station_index,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        # Try to find a session that matches the locker
        # and is in a non-complete and non-active state
        session: Session = Session(await SessionModel.find(
            SessionModel.assigned_locker.station.callsign == callsign,  # pylint: disable=no-member
            SessionModel.assigned_locker.station_index == station_index,  # pylint: disable=no-member
            In(SessionModel.session_state, [
                SessionState.CANCELED,
                SessionState.ABANDONED,
                SessionState.STALE,
                SessionState.EXPIRED]),
            fetch_links=True
        ).first_or_none())
        if session.exists:
            logger.info(
                (f"Station '{callsign}' reported {LockerState.LOCKED} "
                 f"at locker {station_index}, but the assigned session "
                 f"'#{session.id}' is in {session.doc.session_state}."))
            return
        else:
            raise TaskNotFoundException(
                task_type=TaskType.REPORT,
                assigned_station=callsign,
                raise_http=False)

    # 2: Get the affected locker
    locker: Locker = Locker(task.assigned_locker)
    assert locker.exists, f"Locker '#{locker.id}' does not exist."
    logger.info(
        (f"Station '{callsign}' reported {LockerState.LOCKED} "
         f"at locker {station_index} ('#{locker.id}')."))

    # 3: Check if the reported locker matches that of the task
    await task.doc.fetch_link(TaskItemModel.assigned_locker)
    if locker.callsign != task.assigned_locker.callsign:
        raise InvalidLockerReportException(
            locker_id=locker.id, raise_http=False)

    # 4: Check whether the locker was actually registered as unlocked
    if locker.reported_state != LockerState.UNLOCKED.value:
        raise InvalidLockerStateException(
            locker_id=locker.id,
            expected_state=LockerState.UNLOCKED,
            actual_state=locker.reported_state,
            raise_http=False)

    # 5: Find the assigned session
    assert task.assigned_session, f"Task '#{task.id}' has no assigned session."
    session: Session = Session(task.assigned_session)

    assert (session.doc.session_state in [
        SessionState.STASHING,
        SessionState.RETRIEVAL,
        SessionState.CANCELED]
    ), (f"Session '#{session.id}' is in {session.session_state}, expected "
        f"{[SessionState.STASHING, SessionState.ACTIVE, SessionState.RETRIEVAL]}.")

    # 6: If those checks pass, update the locker and create an action
    await locker.register_state(LockerState.LOCKED)

    action_type: ActionType = (
        ActionType.LOCK_AFTER_STASHING if session.doc.session_state == SessionState.STASHING
        else ActionType.LOCK_AFTER_RETRIEVAL)
    await ActionModel(
        assigned_session=session.doc, action_type=action_type).insert()

    # 7: Complete the task and restart the expiration manager
    await task.complete()

    # 8: Catch completed sessions
    next_state: SessionState = session.next_state
    if next_state == SessionState.COMPLETED:
        session.set_state(SessionState.COMPLETED)
        session.doc.completed_at = datetime.now()
        # TODO: Should be redundant with handle_conclude, but is not
        await session.doc.save_changes()
        await session.broadcast_update()
        await ActionModel(
            assigned_session=session.doc, action_type=ActionType.COMPLETE).insert()
        return await session.handle_conclude()

    # Catch canceled sessions
    if session.doc.session_state == SessionState.CANCELED:
        return

    # 9: Await user to return to the locker to pick up his stuff.
    await Task(await TaskItemModel(
        task_type=TaskType.REPORT,
        target=TaskTarget.USER,
        assigned_session=session.doc,
        assigned_station=locker.doc.station,
        assigned_locker=locker.doc,
        timeout_states=[SessionState.ABANDONED],
        moves_session=True,
    ).insert()).activate()
