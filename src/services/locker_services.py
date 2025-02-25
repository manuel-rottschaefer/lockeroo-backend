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
# Models
from src.models.action_models import ActionModel
from src.models.session_models import (
    SessionState,
    ACTIVE_SESSION_STATES,
    PaymentMethod)
from src.models.task_models import (
    TaskItemModel,
    TaskState,
    TaskTarget,
    TaskType)
# Services
from src.services.logging_services import logger_service as logger
# Exceptions
from src.exceptions.task_exceptions import TaskNotFoundException


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
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
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
    await task.complete()

    # 8: Create a queue item for the user to lock the locker
    # TODO: FIXME this is not an optimal solution
    next_state = session.next_state if session.doc.session_state in [
        SessionState.VERIFICATION,
        SessionState.PAYMENT
    ] else SessionState.HOLD

    if next_state == SessionState.HOLD and session.doc.payment_method == PaymentMethod.APP:
        # Also create a task that allows the user to start the
        # payment process without closing the locker
        await Task(await TaskItemModel(
            target=TaskTarget.USER,
            task_type=TaskType.REPORT,
            assigned_user=session.doc.assigned_user,
            assigned_session=session.doc,
            assigned_station=locker.doc.station,
            assigned_locker=locker.doc,
            timeout_states=[SessionState.STALE],
        ).insert()).activate()

    await Task(await TaskItemModel(
        target=TaskTarget.LOCKER,
        task_type=TaskType.REPORT,
        queued_state=next_state,
        assigned_user=session.doc.assigned_user,
        assigned_session=session.doc,
        assigned_station=locker.doc.station,
        assigned_locker=locker.doc,
        timeout_states=[SessionState.STALE],
    ).insert()).activate()


async def handle_lock_report(
        callsign: str, station_index: int) -> None:
    """Process and verify a station report that a locker has been closed"""
    # 1: Find the affected, pending task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.LOCKER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
        TaskItemModel.assigned_station.callsign == callsign,  # pylint: disable=no-member
        TaskItemModel.assigned_locker.station_index == station_index,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        # TODO: Improve error handling here
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
    if locker.doc.locker_state != LockerState.UNLOCKED.value:
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
    await task.complete()

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
            logger.debug(f"Also completing user report task '{user_task.id}'.")
            await user_task.complete()

    # 7: Catch completed sessions
    if session.next_state == SessionState.COMPLETED:
        session.set_state(SessionState.COMPLETED)
        # TODO: Should be redundant with handle_conclude, but is not
        await session.doc.save_changes()
        await session.broadcast_update()
        await ActionModel(
            assigned_session=session.doc,
            action_type=SessionState.COMPLETED).insert()
        return await session.handle_conclude()

    # 8: Catch canceled sessions
    if session.doc.session_state == SessionState.CANCELED:
        return

    # 9: Await user to return to the locker to pick up his stuff.
    await Task(await TaskItemModel(
        task_type=TaskType.REPORT,
        target=TaskTarget.USER,
        assigned_user=session.doc.assigned_user,
        assigned_session=session.doc,
        assigned_station=locker.doc.station,
        assigned_locker=locker.doc,
        timeout_states=[SessionState.ABANDONED],
        queued_state=session.next_state
    ).insert()).activate()
