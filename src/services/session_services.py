"""
Lockeroo.session_services
-------------------------
This module provides utilities and endpoint handlers for session management

Key Features:
    - Import session timeout configuration from .env file
    - Provide session endpoints
    
Dependencies:
    - fastapi
    - fastapi.websockets
    - beanie
"""
# Basics
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import asyncio
# FastAPI & Beanie
from beanie import PydanticObjectId as ObjId, SortDirection
from beanie.operators import In
from fastapi import Response, status
from fastapi.websockets import WebSocket
# Entities
from src.entities.locker_entity import Locker
from src.entities.snapshot_entity import Snapshot
from src.entities.payment_entity import Payment
from src.entities.session_entity import Session
from src.entities.station_entity import Station, TerminalState
from src.entities.task_entity import (
    Task, TaskState, TaskTarget, TaskType)
from src.entities.user_entity import User
# Exceptions
from src.exceptions.session_exceptions import (
    InvalidSessionStateException,
    SessionNotFoundException)
from src.exceptions.station_exceptions import (
    StationNotAvailableException,
    StationNotFoundException)
from src.exceptions.task_exceptions import TaskNotFoundException
from src.exceptions.user_exceptions import (
    UserHasActiveSessionException,
    UserNotAuthorizedException)
from src.exceptions.locker_exceptions import (
    InvalidLockerTypeException,
    LockerNotFoundException)
from src.exceptions.payment_exceptions import InvalidPaymentMethodException
# Models
from lockeroo_models.snapshot_models import SnapshotModel, SnapshotView
from lockeroo_models.locker_models import LockerState
from lockeroo_models.session_models import (
    ACTIVE_SESSION_STATES,
    SessionModel,
    SessionView,
    PaymentMethod,
    SessionState,
    SessionConcludedView,
    SessionBillView
)
from lockeroo_models.station_models import StationModel, StationLocationView
from lockeroo_models.task_models import (
    TaskItemModel, TaskPositionView)
from lockeroo_models.permission_models import PERMISSION
# Services
from src.services.task_services import task_manager
from src.services.websocket_services import websocketmanager
from src.services.config_services import cfg
from src.services.locker_services import LOCKER_TYPES
from src.services.auth_services import permission_check
from src.services.logging_services import logger_service as logger


SESSION_TIMEOUTS: Dict[SessionState, int] = {
    SessionState.CREATED: float(
        cfg.get("SESSION_EXPIRATIONS", 'CREATED', fallback='0')),
    SessionState.PAYMENT_SELECTED: float(
        cfg.get("SESSION_EXPIRATIONS", 'PAYMENT_SELECTED', fallback='0')),
    SessionState.VERIFICATION: float(
        cfg.get("SESSION_EXPIRATIONS", 'VERIFICATION', fallback='0')),
    SessionState.STASHING: float(
        cfg.get("SESSION_EXPIRATIONS", 'STASHING', fallback='0')),
    SessionState.ACTIVE: float(
        cfg.get("SESSION_EXPIRATIONS", 'ACTIVE', fallback='0')),
    SessionState.HOLD: float(
        cfg.get("SESSION_EXPIRATIONS", 'HOLD', fallback='0')),
    SessionState.PAYMENT: float(
        cfg.get("SESSION_EXPIRATIONS", 'PAYMENT', fallback='0')),
    SessionState.RETRIEVAL: float(
        cfg.get("SESSION_EXPIRATIONS", 'RETRIEVAL', fallback='0')),
    SessionState.COMPLETED: float(
        cfg.get("SESSION_EXPIRATIONS", 'COMPLETED', fallback='0')),
    SessionState.CANCELED: float(
        cfg.get("SESSION_EXPIRATIONS", 'CANCELED', fallback='0')),
    SessionState.STALE: float(
        cfg.get("SESSION_EXPIRATIONS", 'STALE', fallback='0')),
    SessionState.EXPIRED: float(
        cfg.get("SESSION_EXPIRATIONS", 'EXPIRED', fallback='0')),
    SessionState.ABORTED: float(
        cfg.get("SESSION_EXPIRATIONS", 'ABORTED', fallback='0')),
}


async def get_details(user: User, session_id: ObjId) -> Optional[SessionView]:
    """Get the details of a session."""
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 2. Get session and verify user.
    session: Session = Session(await SessionModel.get(session_id), session_id)
    await session.doc.fetch_link(SessionModel.assigned_user)
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)

    await session.doc.fetch_all_links()

    # If the session is completed, return the concluded view, otherwise the active view
    if session.session_state in ACTIVE_SESSION_STATES:
        # Fetch a queued task
        task: TaskPositionView = await TaskItemModel.find(
            TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
            TaskItemModel.task_state == TaskState.QUEUED,
            TaskItemModel.expires_at > datetime.now(timezone.utc)
        ).project(TaskPositionView).first_or_none()

        return SessionView.from_document(
            session=session.doc,
            position=task.queue_position if task else 0)

    return SessionConcludedView.from_document(session.doc)


async def get_session_history(user: User, session_id: ObjId) -> Optional[List[SnapshotModel]]:
    """Find all Actions of a session

    Checks if the session exists and whether the user is permitted to access it,
    Then looks up all actions related to the session.

    Args:
        - user (User): The user that is submitting the request
        - session_id (ObjId): The relevant session

    Returns:
        - A List of SnapshotModels successful, else None """
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    session: Session = Session(await SessionModel.get(session_id), session_id)
    if not session.exists:
        raise SessionNotFoundException(user_id=user.fief_id)
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.fief_id)

    accepted_states: List[SessionState] = [
        SessionState.VERIFICATION,
        SessionState.PAYMENT,
        SessionState.STASHING,
        SessionState.RETRIEVAL,
        SessionState.ACTIVE,
        SessionState.HOLD,
        SessionState.COMPLETED,
        SessionState.CANCELED,
        SessionState.ABORTED,
        SessionState.EXPIRED,
        SessionState.STALE,
        SessionState.ABANDONED,
        SessionState.TERMINATED
    ]

    return await SnapshotModel.find(
        SnapshotModel.assigned_session.id == session.doc.id,  # pylint: disable=no-member
        In(SnapshotModel.assigned_session.session_state,  # pylint: disable=no-member
           accepted_states), fetch_links=True).sort(SnapshotModel.timestamp, SortDirection.ASCENDING).project(SnapshotView).to_list()


async def handle_creation_request(
    user: User,
    callsign: str,
    locker_type: str,
    payment_method: Optional[str],
    response: Response
) -> Optional[SessionView]:
    """Handles a request to create a new session submitted by a user.

    Finds the station at which the user wants to create a session.
    Verifies that the user has no active session and is authorized.
    Finds an available locker at the station for the new session.
    Creates a task awaiting a user request to select the payment method.

    Args:
        user (User): The user that is submitting the request
        callsign (str): The callsign of the station where the user wants to create a session
        locker_type (str): The type of locker which the user wants to use

    Returns:
        A SessionView dict if the session could be created

    Raises:
        StationNotFoundException: If the station cannot be found.
        UserHasActiveSessionException: If the user alraedy has an active session.
        UserNotAuthorizedException: If the user is not authorized."""

    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 1: Find the station and confirm its availability
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign
    )
    if not await station.is_available:
        raise StationNotAvailableException(callsign=callsign)

    # 2: Check whether the user exists and is authorized to create a session
    if await user.has_active_session:
        logger.warning(
            f"User '{user.doc.fief_id}' already has an active session.")
        raise UserHasActiveSessionException(user_id=user.id)
    if await user.expired_session_count(timedelta(days=1)) > 2:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)

    # 3: Check whether the given locker type exists
    if locker_type.lower() not in [i.name for i in LOCKER_TYPES]:
        raise InvalidLockerTypeException(locker_type=locker_type)
    locker_type = next(i for i in LOCKER_TYPES if i.name ==
                       locker_type.lower())

    # 4: Check if the user has a locker reservation
    reservation: Task = Task(await TaskItemModel.find(
        TaskItemModel.assigned_station.callsign == station.doc.callsign,  # pylint: disable=no-member
        TaskItemModel.assigned_user.fief_id == user.doc.fief_id,  # pylint: disable=no-member
        TaskItemModel.task_type == TaskType.RESERVATION,
        TaskItemModel.task_state == TaskState.PENDING,
        fetch_links=True
    ).first_or_none())
    if reservation.exists:
        locker: Locker = Locker(reservation.doc.assigned_locker)
        reservation.doc.task_state = TaskState.COMPLETED
        await reservation.doc.save_changes()
    else:
        # 5: Try to find an available locker at the station
        locker: Locker = await Locker().find_available(
            station=station, locker_type=locker_type)
        if not locker.exists:
            response.status_code = status.HTTP_404_NOT_FOUND
            return

    # 6: Create a new session
    initial_state = SessionState.PAYMENT_SELECTED if payment_method else SessionState.CREATED
    session = await Session(SessionModel(
        assigned_user=user.doc,
        assigned_station=station.doc,
        assigned_locker=locker.doc,
        session_state=initial_state,
        payment_method=payment_method
    )).insert()
    await session.doc.fetch_all_links()

    # 7: Check if the session is using a stale locker
    stale_session = await SessionModel.find(
        SessionModel.assigned_locker.id == locker.doc.id,
        SessionModel.session_state == SessionState.STALE
    ).first_or_none()
    if stale_session:
        stale_session = Session(stale_session)
        stale_session.set_state(SessionState.COMPLETED)
        await stale_session.doc.save_changes()
        # locker.doc.locker_state = LockerState.UNLOCKED
        # await locker.doc.save_changes()

    # 7: Await user to select a payment method,
    # request a verification, move straight to stashing
    # or cancel the session
    task: Task = await Task(TaskItemModel(
        target=TaskTarget.USER,
        task_type=TaskType.REPORT,
        assigned_user=user.doc,
        assigned_session=session.doc,
        assigned_station=station.doc,
        timeout_states=[SessionState.EXPIRED],
    )).insert()
    await task.activate(task_manager=task_manager)

    # 8: Log the action
    await Snapshot(SnapshotModel(
        assigned_session=session.doc,
        session_state=session.doc.session_state,
    )).insert()

    return SessionView.from_document(session.doc)


async def handle_payment_selection(
    session_id: ObjId,
    user: User,
    payment_method: str
) -> Optional[SessionView]:
    """Handles a request to select the payment method for a session submitted by a user.

    Finds the task awaiting the user action.
    If such a task is found, the session state and user authorization is validated.
    Finally, the payment method is assigned to the session, the user task completed
    and a new task awaiting the verification request created.

    Args:
        session_id (ObjId): The ID of the session to be assigned a payment method
        user (User): The user that is submitting the request

    Returns:
        A SessionView dict if the session exists and a payment method could be assigned

    Raises:
        TaskNotFoundException: If the user task is not found.
        SessionNotFoundException: If no session could be found.
        UserNotAuthorizedException: If the user is not authorized.
        InvalidSessionStateException: If the session is not in CREATED state."""

    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 1: Find the related task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.USER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        # Try to find the session
        session: SessionModel = await SessionModel.get(session_id)
        if not session:
            raise SessionNotFoundException(user_id=user.id)
        await session.fetch_link(SessionModel.assigned_station)
        raise TaskNotFoundException(
            task_type=TaskType.REPORT,
            assigned_station=session.assigned_station,
            raise_http=False)

    # 2: Check if the payment method has not been selected
    if task.assigned_session.payment_method:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionState.CREATED],
            actual_state=task.assigned_session.session_state)
    # TODO: Evaluate if we need to re-check they payment method
    # payment_method: str = payment_method.lower()
    # if payment_method not in PaymentType:
    #    raise InvalidPaymentMethodException(
    #        session_id=session_id,
    #        payment_method=payment_method)

    # 3: Fetch the assigned session and verify its state
    await task.doc.fetch_link(TaskItemModel.assigned_session)
    session: Session = Session(task.assigned_session)

    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)
    if session.session_state != SessionState.CREATED:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionState.CREATED],
            actual_state=session.session_state)

    # 4: Complete previous task
    await task.complete(task_manager=task_manager)

    # 5: Assign the payment method to the session
    session.payment_method = payment_method
    logger.debug(
        (f"Payment method '{payment_method.upper()}' "
         f"assigned to session '#{session.id}'."), session_id=session.id)

    session.set_state(SessionState.PAYMENT_SELECTED)
    await session.doc.save_changes()

    # 6: Await the user to request payment
    task = await Task(TaskItemModel(
        target=TaskTarget.USER,
        task_type=TaskType.REPORT,
        assigned_user=task.doc.assigned_user,
        assigned_session=session.doc,
        assigned_station=session.assigned_station,
        timeout_states=[SessionState.EXPIRED],
    )).insert()
    await task.activate(task_manager=task_manager)

    return SessionView.from_document(session.doc)


async def handle_verification_request(
    session_id: ObjId,
    user: User
) -> Optional[SessionView]:
    """Handles a verification request submitted by a user.

    Finds the task that is awaiting the user request.
    If such a task is found, the session state and user authorization is validated.
    Finally, the user task is completed and a new task,
    awaiting the station confirmation, is created.

    Args:
        session_id (ObjId): The ID of the session
        user (User): The user that is submitting the request

    Returns:
        A SessionView dict if the session exists.

    Raises:
        TaskNotFoundException: If no task awaiting the user request has been found.
        SessionNotFoundException: If the session is not found.
        UserNotAuthorizedException: If the user is not authorized.
        InvalidSessionStateException: If the session is not active or on hold."""
    # 1: Verify permissions
    # permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 1: Find the assigned task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.USER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        raise TaskNotFoundException(
            task_type=TaskType.REPORT,
            assigned_station=None,
            raise_http=False)

    # 2: Get the assigned session and verify its state
    await task.doc.fetch_all_links()
    session: Session = Session(task.assigned_session)

    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)
    if session.session_state != SessionState.PAYMENT_SELECTED:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionState.PAYMENT_SELECTED],
            actual_state=session.session_state)

    # 3: Find the assigned station
    if not session.assigned_station:
        raise StationNotFoundException(station_id=session.assigned_station.id)

    # 4: Launch a verification process at the station or via the app
    await task.complete(task_manager=task_manager)
    if session.payment_method == PaymentMethod.TERMINAL:
        new_task = await Task(TaskItemModel(
            target=TaskTarget.TERMINAL,
            task_type=TaskType.CONFIRMATION,
            assigned_session=session.doc,
            assigned_user=session.doc.assigned_user,
            assigned_station=session.assigned_station,
            timeout_states=[SessionState.ABORTED],
            queued_state=TerminalState.VERIFICATION
        )).insert()
        queue_pos = await new_task.get_queue_position()

        await new_task.evaluate_queue(task_manager=task_manager)
    else:
        session.set_state(session.next_state)
        await session.doc.save_changes()
        queue_pos = 0

    return SessionView.from_document(session.doc, position=queue_pos)


async def handle_hold_request(
        session_id: ObjId, user: User) -> Optional[SessionView]:
    """Handles a request to hold the current session submitted by a user.

    Finds the session that the user wants to hold.
    If such a session is found, verify the state and payment method.
    Finally, create a task for the station to confirm the unlock.

    Args:
        session_id (ObjId): The ID of the session
        user (User): The user that is submitting the request

    Returns:
        A SessionView dict if the session exists.

    Raises:
        SessionNotFoundException: If the session is not found.
        UserNotAuthorizedException: If the user is not authorized.
        InvalidSessionStateException: If the session is not active or on hold.
        InvalidPaymentMethodException: If the payment method does not allow holding."""
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 2: Find the task awaiting a user action
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.USER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        raise TaskNotFoundException(
            task_type=TaskType.REPORT,
            assigned_station=None,
            raise_http=False)

    # 3: Find the session and check whether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id), session_id)
    await session.doc.fetch_all_links()
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)

    # 4: Get the assigned session and verify its state
    await task.doc.fetch_all_links()
    session: Session = Session(task.assigned_session)

    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)
    if session.session_state != SessionState.ACTIVE:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionState.ACTIVE],
            actual_state=session.session_state)

    # 5: Check whether the user has chosen the app method for payment.
    if session.payment_method == PaymentMethod.TERMINAL:
        raise InvalidPaymentMethodException(
            session_id=session_id,
            payment_method=session.payment_method)

    # 6: Get the locker and assign an open request
    locker: Locker = Locker(session.assigned_locker)
    if not locker.exists:
        raise LockerNotFoundException(
            locker_id=session.assigned_locker)

    # 7: Complete the previous task, then instruct locker to open
    await task.complete(task_manager=task_manager)
    task = await Task(TaskItemModel(
        target=TaskTarget.LOCKER,
        task_type=TaskType.CONFIRMATION,
        assigned_session=session.doc,
        assigned_user=session.doc.assigned_user,
        assigned_station=session.doc.assigned_station,
        assigned_locker=session.doc.assigned_locker,
        queued_state=LockerState.UNLOCKED,
        timeout_states=[SessionState.ACTIVE,
                        SessionState.ABORTED],
    )).insert()
    await task.activate(task_manager=task_manager)

    return SessionView.from_document(session.doc)


async def handle_payment_request(session_id: ObjId, user: User) -> Optional[SessionView]:
    """Handles a payment request submitted by a user."""
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 2: Find the session and check whether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id), session_id)
    await session.doc.fetch_all_links()
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)

    # 3: Launch the payment initiation handler depending on the selected payment method
    if session.doc.payment_method == PaymentMethod.TERMINAL:
        await handle_terminal_payment_request(session, user)

    else:
        await handle_app_payment_request(session, user)

    return SessionView.from_document(session.doc)


async def handle_app_payment_request(session: Session, user: User) -> Optional[SessionView]:
    """Handles a payment request submitted by a user."""
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 2: Find the pending task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.USER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_session.id == session.doc.id,  # pylint: disable=no-member
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
        # TaskItemModel.assigned_user.id == user.doc.id,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        if not session.exists:
            raise SessionNotFoundException(user_id=user.fief_id)
        raise TaskNotFoundException(
            task_type=TaskType.REPORT,
            assigned_station=session.assigned_station.id,
            raise_http=False)

    # 3: Check if the session is in the correct state for an app payment.
    expected_states = [
        SessionState.ACTIVE,
        SessionState.HOLD
    ]
    if session.doc.session_state not in expected_states:
        raise InvalidSessionStateException(
            session_id=session.id,
            expected_states=expected_states,
            actual_state=session.doc.session_state)

    # 4: Also end pending locker tasks
    locker_tasks = await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.LOCKER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        # In(TaskItemModel.task_state, [TaskState.QUEUED, TaskState.PENDING]),
        TaskItemModel.assigned_session.id == session.doc.id,  # pylint: disable=no-member
    ).to_list()

    for locker_task in locker_tasks:
        await Task(locker_task).cancel(task_manager=task_manager)

    # 5: Move the session to the next state.
    session.set_state(SessionState.PAYMENT)
    await session.doc.save_changes()

    # 6: Set the task to completed
    task.doc.task_state = TaskState.COMPLETED
    await task.doc.save_changes()


async def handle_terminal_payment_request(session: Session, user: User) -> Optional[SessionView]:
    """Handles a payment request submitted by a user.

    Finds a pending task that is awaiting such a request.
    If such a task exists, a payment at the assigned station is initiated
    and a new task awaiting confirmation is created.

    Args:
        session_id (ObjId): The ID of the session
        user (User): The user that is submitting the request

    Returns:
        A SessionView dict if the session exists.

    Raises:
        TaskNotFoundException: If no task is found.
        UserNotAuthorizedException: If the user is not authorized.
        InvalidSessionStateException: If the session is not active or on hold."""
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 2: Find the task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.USER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_session.id == session.doc.id,  # pylint: disable=no-member
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
        # TaskItemModel.assigned_user.id == user.doc.id,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        if not session.exists:
            raise SessionNotFoundException(user_id=user.fief_id)
        raise TaskNotFoundException(
            task_type=TaskType.REPORT,
            assigned_station=session.assigned_station.id,
            raise_http=False)

    # 3: Check if the session is in the correct state
    ACCEPTED_STATES = [SessionState.ACTIVE,  # pylint: disable=invalid-name
                       SessionState.HOLD]
    if session.session_state not in ACCEPTED_STATES:
        raise InvalidSessionStateException(
            session_id=session.id,
            expected_states=ACCEPTED_STATES,
            actual_state=session.session_state)

    # 4: Set the task to completed
    task.doc.task_state = TaskState.COMPLETED
    await task.doc.save_changes()

    # Calculate session durations
    await session.calc_durations()

    # 5: Create a payment object
    payment: Payment = await Payment().create(session=session.doc)
    session.doc.price = await payment.current_price(session.doc)
    await session.doc.save_changes()

    # 6: Await station to enable terminal
    task = await Task(TaskItemModel(
        target=TaskTarget.TERMINAL,
        task_type=TaskType.CONFIRMATION,
        assigned_session=session.doc,
        assigned_user=session.doc.assigned_user,
        assigned_station=session.doc.assigned_station,
        timeout_states=[session.session_state,
                        SessionState.EXPIRED],
        queued_state=TerminalState.PAYMENT
    )).insert()
    await task.evaluate_queue(task_manager=task_manager)


async def handle_verification_completion(
        session_id: ObjId, user: User) -> Optional[SessionView]:
    """Handles a verification completion request submitted by a user.
    Finds the session that the user wants to complete the verification for.
    If such a session is found, the user authorization is confirmed,
    the session state is updated and a new task awaiting the verification request is created.

    Args:
        session_id (ObjId): The ID of the session
        user (User): The user that is submitting the request
    Returns:
        A SessionView dict if the session exists.
    Raises:
        SessionNotFoundException: If the session is not found.
    """
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 2: Find the session and check whether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id), session_id)
    await session.doc.fetch_all_links()
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)

    # 3: Check if the session is in the correct state
    accepted_states = [SessionState.VERIFICATION]
    if session.doc.session_state not in accepted_states:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=accepted_states,
            actual_state=session.doc.session_state)

    # 4: Check if the session has the correct payment method
    if session.payment_method == PaymentMethod.TERMINAL:
        raise InvalidPaymentMethodException(
            session_id=session_id,
            payment_method=session.payment_method)

    # 5: Get the locker and assign an open request
    locker: Locker = Locker(session.assigned_locker)
    if not locker.exists:
        raise LockerNotFoundException(locker_id=session.assigned_locker)

    task = await Task(TaskItemModel(
        target=TaskTarget.LOCKER,
        task_type=TaskType.CONFIRMATION,
        assigned_session=session.doc,
        assigned_user=session.doc.assigned_user,
        assigned_station=session.doc.assigned_station,
        assigned_locker=session.doc.assigned_locker,
        timeout_states=[SessionState.ABORTED],
        queued_state=LockerState.UNLOCKED
    )).insert()
    await task.activate(task_manager=task_manager)

    return SessionView.from_document(session.doc)


async def handle_payment_completion(
        session_id: ObjId, user: User) -> Optional[SessionView]:
    """Handles a payment completion request submitted by a user.
    A payment completion request can only be submitted for sessions
    that are not using terminal payment.

    Finds the session that the user wants to complete the payment for.
    If such a session is found, the user authorization is confirmed,
    the session state is updated and a new task awaiting the verification request is created.

    Args:
        session_id (ObjId): The ID of the session
        user (User): The user that is submitting the request

    Returns:
        A SessionView dict if the session exists.

    Raises:
        SessionNotFoundException: If the session is not found.
        UserNotAuthorizedException: If the user is not authorized.
        InvalidSessionStateException: If the session is not active or on hold.
    """
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 2: Find the session and check whether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id), session_id)
    await session.doc.fetch_all_links()
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)

    # 3: Check if the session is in the correct state
    accepted_states = [SessionState.PAYMENT]
    if session.session_state not in accepted_states:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=accepted_states,
            actual_state=session.session_state)

    # 4: Check if the session has the correct payment method
    if session.payment_method != PaymentMethod.TERMINAL:
        raise InvalidPaymentMethodException(
            session_id=session_id,
            payment_method=session.payment_method)

    # 5: Get the locker and assign an open request
    locker: Locker = Locker(session.assigned_locker)
    if not locker.exists:
        raise LockerNotFoundException(locker_id=session.assigned_locker)

    # 6: Find the alternative locker close task and complete it
    close_task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.LOCKER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
    ).first_or_none())
    if close_task.exists:
        await close_task.complete(task_manager=task_manager)

    # 7: Create a tasks that waits for the locker to open
    if locker.doc.locker_state == LockerState.LOCKED:
        task = await Task(TaskItemModel(
            target=TaskTarget.LOCKER,
            task_type=TaskType.CONFIRMATION,
            assigned_session=session.doc,
            assigned_user=session.doc.assigned_user,
            assigned_station=session.doc.assigned_station,
            assigned_locker=session.doc.assigned_locker,
            timeout_states=[SessionState.ACTIVE,
                            SessionState.ABORTED],
            queued_state=LockerState.UNLOCKED
        )).insert()
        await task.activate(task_manager=task_manager)

    else:
        session.set_state(SessionState.RETRIEVAL)
        await session.doc.save_changes()
        # Wait for station to report locker close
        task = await Task(TaskItemModel(
            target=TaskTarget.LOCKER,
            task_type=TaskType.REPORT,
            assigned_session=session.doc,
            assigned_user=session.doc.assigned_user,
            assigned_station=session.doc.assigned_station,
            assigned_locker=session.doc.assigned_locker,
            timeout_states=[SessionState.EXPIRED],
            queued_state=LockerState.LOCKED
        )).insert()
        await task.activate(task_manager=task_manager)

    return SessionView.from_document(session.doc)


async def handle_cancel_request(session_id: ObjId, user: User
                                ) -> Optional[SessionConcludedView]:
    """Handles a cancelation request submitted by a user.

    Finds the session that should be canceled.
    If such a session exists, authorization is confirmed,
    and the session and all related tasks are updated.

    Args:
        session_id (ObjId): The ID of the session
        user (User): The user that is submitting the request

    Returns:
        A SessionConcludedView dict if the session exists.

    Raises:
        SessionNotFoundException: If the session is not found
        UserNotAuthorizedException: If the user is not authorized
        InvalidSessionStateException: If the session is not in a suitable state.
    """
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_MODIFY], user.doc.permissions)

    # 2: Find the session and check whether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id), session_id)

    await session.doc.fetch_link(SessionModel.assigned_user)
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.doc.fief_id)

    # 3: Check if session is in correct state
    accepted_states: list = [
        SessionState.CREATED,
        SessionState.PAYMENT_SELECTED,
        SessionState.VERIFICATION,
        SessionState.STASHING,
    ]
    if session.session_state not in accepted_states:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=accepted_states,
            actual_state=session.session_state)

    # 4: Check if there are any queued or pending tasks assigned to the session
    tasks = await TaskItemModel.find(
        TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
        In(TaskItemModel.task_state, [TaskState.QUEUED, TaskState.PENDING]),
        fetch_links=True
    ).to_list()

    for task in tasks:
        await Task(task).cancel(task_manager=task_manager)

    # 5: Conclude session, create action and broadcast update
    await session.handle_conclude(SessionState.CANCELED)
    await Snapshot(SnapshotModel(
        assigned_session=session.doc,
        session_state=SessionState.CANCELED
    )).insert()

    return SessionConcludedView.from_document(session.doc)


async def get_session_bill(session_id: ObjId, user: User) -> Optional[SessionBillView]:
    """Handles a request to get the bill view for a session."""
    # Find the session in the database
    session: Session = Session(await SessionModel.get(session_id), session_id)
    await session.doc.fetch_link(SessionModel.assigned_station)
    # convert station to stationlocationview
    station = StationLocationView.from_document(session.doc.assigned_station)

    # Find all snapshots of the session
    snapshots = await SnapshotModel.find(
        SnapshotModel.assigned_session.id == session.doc.id,  # pylint: disable=no-member

        fetch_links=True
    ).sort(SnapshotModel.timestamp).project(SnapshotView).to_list()

    # Create the bill view
    bill_view = SessionBillView.from_documents(
        session=session.doc, station=station, snapshots=snapshots)
    return bill_view


async def handle_update_subscription_request(
    socket: WebSocket
):
    """
    Handles a subscription request submitted by a user.

    Validates session and user, registers the websocket connection,
    and maintains a subscription loop until the connection is closed or ends.

    Raises:
        SessionNotFoundException
        UserNotAuthorizedException
        InvalidSessionStateException
    """
    # Await first auth message
    await socket.accept()
    data = await socket.receive_json()
    user_id = data.get("user_id")
    session_id = data.get("session_id")
    session_token = data.get("session_token")

    logger.info(
        (f"User '{user_id}' is trying to "
         f"subscribe."),
        session_id=session_id)

    # 1. Load session
    session = Session(await SessionModel.get(session_id), session_id)
    if not session.exists:
        await socket.close(code=1008)
        raise SessionNotFoundException(user_id=user_id)

    # 2. Load and validate assigned user
    await session.doc.fetch_link(SessionModel.assigned_user)
    # if session.doc.assigned_user.fief_id != user_id:
    #    await socket.close(code=1008)
    #    raise UserNotAuthorizedException(user_id=user_id)

    # 3. Validate websocket token
    if session.doc.websocket_token != session_token:
        await socket.close(code=1008)
        raise UserNotAuthorizedException(user_id=user_id)

    # 4. Ensure session is in valid state
    if session.doc.session_state not in ACTIVE_SESSION_STATES:
        await socket.close(code=1008)
        raise InvalidSessionStateException(
            session_id=session.id,
            expected_states=ACTIVE_SESSION_STATES,
            actual_state=session.doc.session_state
        )

    # 6. Register connection
    websocketmanager.register_connection(session.doc.id, socket)
    logger.debug(
        f"WebSocket connection accepted for session '{session.doc.id}'.", session_id=session.doc.id)

    # 7. Send creation snapshot
    creation_snapshot: SnapshotModel = await SnapshotModel.find(
        SnapshotModel.assigned_session.id == session.doc.id,
        fetch_links=True,
    ).sort(SnapshotModel.timestamp).project(SnapshotView).first_or_none()
    if creation_snapshot:
        await websocketmanager.send_text(
            creation_snapshot.assigned_session,
            creation_snapshot.model_dump())

    # 7. Maintain subscription loop
    # websocketmanager.handle_socket_session(session_id=session.doc.id)
    # TODO: Hook this up to websocket manager
    while True:
        try:
            await asyncio.wait_for(socket.receive_bytes(), timeout=0.2)
        except asyncio.TimeoutError:
            if websocketmanager.get_connection(session_id) is None:
                logger.debug(
                    f"Session {session_id} websocket connection closed.", session_id=session_id)
                break
        except Exception as e:
            logger.error(
                f"Error in keep-alive loop for session '{session_id}': {e}")
            break
