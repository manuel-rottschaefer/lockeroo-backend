"""Provides utility functions for the sesssion management backend."""
# Basics
from datetime import datetime
# Types
from datetime import timedelta
from typing import List, Optional
from uuid import UUID
# Beanie
from beanie import PydanticObjectId as ObjId, SortDirection
from beanie.operators import In
# Websockets
from fastapi.websockets import (
    WebSocket,
    WebSocketDisconnect)
# Entities
from src.entities.locker_entity import Locker
from src.entities.payment_entity import Payment
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.task_entity import (
    Task,
    TaskState,
    TaskTarget,
    TaskType)
from src.entities.user_entity import User
from src.exceptions.locker_exceptions import (
    InvalidLockerTypeException,
    LockerNotAvailableException,
    LockerNotFoundException)
from src.exceptions.payment_exceptions import InvalidPaymentMethodException
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
from src.models.action_models import ActionModel, ActionType
from src.models.locker_models import LOCKER_TYPES
from src.models.session_models import (
    ACTIVE_SESSION_STATES,
    SessionView,
    ConcludedSessionView,
    CreatedSessionView,
    ActiveSessionView,
    PaymentTypes,
    SessionModel,
    SessionState)
from src.models.station_models import StationModel
# Models
from src.models.task_models import TaskItemModel
from src.services import websocket_services
# Services
from src.services.logging_services import logger_service as logger


async def get_details(session_id: ObjId, user: User) -> Optional[SessionView]:
    """Get the details of a session."""
    session: Session = Session(await SessionModel.get(session_id), session_id)

    await session.doc.fetch_link(SessionModel.assigned_user)
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)

    await session.doc.fetch_all_links()

    # If the session is completed, return the concluded view, otherwise the active view
    if session.session_state in ACTIVE_SESSION_STATES:
        # Fetch a queued task
        task: Task = Task(await TaskItemModel.find(
            TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
            TaskItemModel.task_state == TaskState.QUEUED,
            TaskItemModel.expires_at > datetime.now()
        ).first_or_none())

        return ActiveSessionView(
            id=str(session.doc.id),
            assigned_user=session.doc.assigned_user.fief_id,
            station=session.doc.assigned_station.callsign,
            locker_index=session.doc.assigned_locker.station_index,
            service_type=session.doc.session_type,
            session_state=session.doc.session_state,
            queue_position=task.queue_position if task.exists else 0
        )

    return ConcludedSessionView(
        id=str(session.doc.id),
        station=session.doc.assigned_station.callsign,
        locker_index=session.doc.assigned_locker.station_index,
        service_type=session.doc.session_type,
        session_state=session.doc.session_state,
        total_duration=session.doc.total_duration.total_seconds()
    )


async def get_session_history(session_id: ObjId, user: User) -> Optional[List[ActionModel]]:
    """Get all actions of a session."""
    session: Session = Session(await SessionModel.get(session_id), session_id)
    if not session.exists:
        raise SessionNotFoundException(user_id=user.fief_id)
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.fief_id)

    return await ActionModel.find(
        ActionModel.assigned_session == session_id
    )


async def handle_creation_request(
    user: User,
    callsign: str,
    locker_type: str,
    payment_method: Optional[str],
) -> Optional[CreatedSessionView]:
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
            f"User '#{user.id}' already has an active session.")
        raise UserHasActiveSessionException(user_id=user.id)
    if await user.get_expired_session_count(timedelta(days=1)) > 2:
        raise UserNotAuthorizedException(user_id=user.id)

    # 3: Check whether the given locker type exists
    if locker_type.lower() not in [i.name for i in LOCKER_TYPES]:
        raise InvalidLockerTypeException(locker_type=locker_type)
    locker_type = next(i for i in LOCKER_TYPES if i.name ==
                       locker_type.lower())

    # 4: Check if the user has a locker reservation
    reservation: Task = Task(await TaskItemModel.find(
        # TaskItemModel.assigned_station.callsign == station.doc.callsign,  # pylint: disable=no-member
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
            raise LockerNotAvailableException(
                station_callsign=callsign,
                locker_type=locker_type)

    # 6: Create a new session
    initial_state = SessionState.PAYMENT_SELECTED if payment_method else SessionState.CREATED
    session = Session(await SessionModel(
        assigned_user=user.doc,
        assigned_station=station.doc,
        assigned_locker=locker.doc.id,
        session_state=initial_state,
        payment_method=payment_method
    ).insert())

    # 7: Await user to select a payment method,
    # request a verification, move straight to stashing
    # or cancel the session
    task: Task = Task(await TaskItemModel(
        target=TaskTarget.USER,
        task_type=TaskType.REPORT,
        assigned_user=user.doc,
        assigned_session=session.doc,
        assigned_station=station.doc,
        timeout_states=[SessionState.EXPIRED],
        moves_session=False
    ).insert())
    await task.activate()

    # 8: Log the action
    await ActionModel(
        assigned_session=session.doc, action_type=ActionType.CREATE).insert()

    return session.created_view


async def handle_payment_selection(
    session_id: ObjId,
    user: User,
    payment_method: str
) -> Optional[ActiveSessionView]:
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

    # 1: Find the related task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.USER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
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
    # if payment_method not in PaymentTypes:
    #    raise InvalidPaymentMethodException(
    #        session_id=session_id,
    #        payment_method=payment_method)

    # 3: Fetch the assigned session and verify its state
    await task.doc.fetch_link(TaskItemModel.assigned_session)
    session: Session = Session(task.assigned_session)

    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)
    if session.session_state != SessionState.CREATED:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionState.CREATED],
            actual_state=session.session_state)

    # 4: Complete previous task
    await task.complete()

    # 5: Assign the payment method to the session
    session.payment_method = payment_method
    logger.debug(
        (f"Payment method '{payment_method.upper()}' "
         f"assigned to session '#{session.id}'.")
    )
    session.set_state(SessionState.PAYMENT_SELECTED)
    await session.doc.save_changes()

    # 6: Await the user to request payment
    await Task(await TaskItemModel(
        target=TaskTarget.USER,
        task_type=TaskType.REPORT,
        assigned_user=task.doc.assigned_user,
        assigned_session=session.doc,
        assigned_station=session.assigned_station,
        timeout_states=[SessionState.EXPIRED],
        moves_session=False
    ).insert()).activate()

    return ActiveSessionView(
        id=str(session.doc.id),
        assigned_user=session.doc.assigned_user.fief_id,
        station=session.doc.assigned_station.callsign,
        locker_index=session.doc.assigned_locker.station_index,
        service_type=session.doc.session_type,
        session_state=session.doc.session_state,
        queue_position=0
    )


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
    # 1: Find the assigned task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.USER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
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
    # await session.doc.sync()

    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)
    if session.session_state != SessionState.PAYMENT_SELECTED:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionState.PAYMENT_SELECTED],
            actual_state=session.session_state)

    # 3: Find the assigned station
    if not session.assigned_station:
        raise StationNotFoundException(station_id=session.assigned_station.id)

    # 4: Complete the previous task and create a new one
    await task.complete()
    await Task(await TaskItemModel(
        target=TaskTarget.TERMINAL,
        task_type=TaskType.CONFIRMATION,
        assigned_user=session.doc.assigned_user,
        assigned_session=session.doc,
        assigned_station=session.assigned_station,
        timeout_states=[SessionState.ABORTED],
        moves_session=False
    ).insert()).evaluate_queue_state()

    await ActionModel(
        assigned_session=session.doc, action_type=ActionType.REQUEST_VERIFICATION).insert()

    return await session.view


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
    # 1: Find the session and check whether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id), session_id)
    await session.doc.assigned_user.fetch_link(SessionModel.assigned_user)
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)

    # 2: Check whether the session is active
    if session.session_state != SessionState.ACTIVE:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionState.ACTIVE],
            actual_state=session.session_state)

    # 3: Check whether the user has chosen the app method for payment.
    if session.payment_method == PaymentTypes.TERMINAL:
        raise InvalidPaymentMethodException(
            session_id=session_id,
            payment_method=session.payment_method)

    # 4: Get the locker and assign an open request
    locker: Locker = await Locker(session.assigned_locker)
    if not locker.exists:
        raise LockerNotFoundException(locker_id=session.assigned_locker)

    # 5: Create the task awaiting station confirmation of unlocking
    await Task(TaskItemModel(
        target=TaskTarget.LOCKER,
        task_type=TaskType.CONFIRMATION,
        assigned_user=session.doc.assigned_user,
        assigned_station=session.doc.assigned_station,
        assigned_session=session.doc,
        assigned_locker=locker.doc,
        timeout_states=[SessionState.ACTIVE, SessionState.ABORTED],
        moves_session=False
    ).insert()).evaluate_queue_state()

    await ActionModel(
        assigned_session=session.doc, action_type=ActionType.REQUEST_HOLD).insert()

    return await session.view


async def handle_payment_request(session_id: ObjId, user: User) -> Optional[SessionView]:
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
    # 1: Find the task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.USER,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        # Get the session by ID
        session: SessionModel = await SessionModel.get(session_id)
        await session.fetch_link(SessionModel.assigned_station)
        if not session.exists():
            raise SessionNotFoundException(user_id=user.fief_id)
        raise TaskNotFoundException(
            task_type=TaskType.REPORT,
            assigned_station=session.assigned_station.id,
            raise_http=False)

    # 2: Get the assigned session and station
    # await task.doc.fetch_link(TaskItemModel.assigned_session)
    session: Session = Session(task.assigned_session)

    # 3: Validate session result
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)

    ACCEPTED_STATES = [SessionState.ACTIVE,  # pylint: disable=invalid-name
                       SessionState.HOLD]
    if session.session_state not in ACCEPTED_STATES:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=ACCEPTED_STATES,
            actual_state=session.session_state)

    #  3: Set the task to completed
    task.doc.task_state = TaskState.COMPLETED

    # 4: Create a payment object
    await task.doc.save_changes()
    await Payment().create(session=session.doc)

    # 5: Await station to enable terminal
    await Task(await TaskItemModel(
        target=TaskTarget.TERMINAL,
        task_type=TaskType.CONFIRMATION,
        assigned_user=session.doc.assigned_user,
        assigned_session=session.doc,
        assigned_station=session.assigned_station,
        timeout_states=[session.session_state,
                        SessionState.EXPIRED],
        moves_session=False,
    ).insert()).evaluate_queue_state()

    # 6: Log the request
    await ActionModel(
        assigned_session=session.doc, action_type=ActionType.REQUEST_PAYMENT).insert()

    return await session.view


async def handle_cancel_request(session_id: ObjId, user: User
                                ) -> Optional[ConcludedSessionView]:
    """Handles a cancelation request submitted by a user.

    Finds the session that should be canceled.
    If such a session exists, authorization is confirmed,
    and the session and all related tasks are updated.

    Args:
        session_id (ObjId): The ID of the session
        user (User): The user that is submitting the request

    Returns:
        A ConcludedSessionView dict if the session exists.

    Raises:
        SessionNotFoundException: If the session is not found
        UserNotAuthorizedException: If the user is not authorized
        InvalidSessionStateException: If the session is not in a suitable state."""
    # 1: Find the session and check whether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id), session_id)

    await session.doc.fetch_link(SessionModel.assigned_user)
    if session.doc.assigned_user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)

    # 2: Check if session is in correct state
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

    # 3: Check if there are any queued or pending tasks assigned to the session
    tasks = await TaskItemModel.find(
        TaskItemModel.assigned_session.id == session_id,  # pylint: disable=no-member
        In(TaskItemModel.task_state, [TaskState.QUEUED, TaskState.PENDING]),
        fetch_links=True
    ).to_list()

    for task in tasks:
        await Task(task).cancel()

    # 4: Update session state and log the action
    session.set_state(SessionState.CANCELED)
    session.doc.total_duration = await session.total_duration
    session.doc.active_duration = await session.active_duration
    await session.doc.save_changes()
    await session.broadcast_update()
    await session.handle_conclude()
    await ActionModel(
        assigned_session=session.doc, action_type=ActionType.REQUEST_CANCEL).insert()

    return ConcludedSessionView(
        id=str(session.id),
        station=session.assigned_station.callsign,
        locker_index=session.assigned_locker.station_index,
        service_type=session.session_type,
        session_state=session.session_state,
        total_duration=session.doc.total_duration.total_seconds(),
        active_duration=session.doc.active_duration.total_seconds()
    )


async def handle_update_subscription_request(
        session_id: ObjId, session_token: str, user_id: UUID, socket: WebSocket) -> None:
    """Handles a subscription request submitted by a user.

    Finds the session that the user wants to subscribe to.
    If such a session is found, the subscription is registered
    with the websocket service and the update stream is initated.

    Args:
        session_id (ObjId): The ID of the session
        socket (WebSocket): The websocket instance passed with the request
        user (User): The user that is submitting the request

    Returns:
        A SessionView dict if the session exists.

    Raises:
        SessionNotFoundException: If the session is not found.
        UserNotAuthorizedException: If the user is not authorized.
        InvalidSessionStateException: If the session is not active or on hold."""
    # 1: Check whether the session exists
    session: Session = Session(await SessionModel.get(session_id), session_id)
    if not session.exists:
        await socket.close(code=1008)
        raise SessionNotFoundException(user_id=user_id)
    await session.doc.fetch_link(SessionModel.assigned_user)
    if session.doc.assigned_user.fief_id != UUID(user_id):
        await socket.close(code=1008)
        raise UserNotAuthorizedException(user_id=user_id)
    if session.doc.websocket_token != session_token:
        await socket.close(code=1008)
        raise UserNotAuthorizedException(user_id=user_id)
    if session.doc.session_state not in ACTIVE_SESSION_STATES:
        raise InvalidSessionStateException(
            session_id=session.id,
            expected_states=ACTIVE_SESSION_STATES,
            actual_state=session.doc.session_state)

    # 2: Check whether the websocket connection already exists
    if websocket_services.get_connection(session.id):
        logger.debug(
            f"Session '#{session.id}' cannot have more than one update subscription.")
        # Close the WebSocket connection with a normal closure code
        await socket.close(code=1000)
        return

    # 3: Check if the session is not in an inactive state
    if session.session_state not in ACTIVE_SESSION_STATES:
        logger.debug(
            f"Session '#{session.id}' is not offering updates anymore.")
        # Close the WebSocket connection with a normal closure code
        await socket.close(code=1000)
        return

    # 4: Register the connection
    await socket.accept()
    websocket_services.register_connection(session.id, socket)
    # logger.debug(
    #    ("Subscription has been ACTIVATED for "
    #     f"session '#{session.id}'."))

    try:
        while True:
            await socket.receive_bytes()

    # 5: Register a disconnect event
    except WebSocketDisconnect:
        #    logger.debug(
        #        ("Subscription has been DEACTIVATED for "
        #         f"session '#{session.id}' at station."))
        websocket_services.unregister_connection(session.id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error in ws for session '#{
                     session.id}': {e}")
        # Close the WebSocket connection with an internal error code
        await socket.close(code=1006)
        websocket_services.unregister_connection(session.id)
