"""Provides utility functions for the sesssion management backend."""
# Types
from typing import List, Optional
from datetime import timedelta
# FastAPI
from fastapi.websockets import WebSocket, WebSocketDisconnect
# Beanie
from beanie import PydanticObjectId as ObjId, SortDirection
# Entities
from src.entities.locker_entity import Locker
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.payment_entity import Payment
from src.entities.user_entity import User
from src.entities.task_entity import Task, TaskState, TaskType, TaskTarget
# Models
from src.models.task_models import TaskItemModel
from src.models.station_models import StationModel
from src.models.action_models import ActionModel
from src.models.session_models import (
    SessionModel, PaymentTypes,
    SessionState, SessionView,
    ACTIVE_SESSION_STATES)
# Services
from src.services.action_services import create_action
from src.services.locker_services import LOCKER_TYPES
from src.services.logging_services import logger
import src.services.websocket_services as websocket_services
# Exceptions
from src.exceptions.session_exceptions import (
    SessionNotFoundException, InvalidSessionStateException)
from src.exceptions.station_exceptions import (
    StationNotFoundException, StationNotAvailableException)
from src.exceptions.locker_exceptions import (
    LockerNotFoundException, LockerNotAvailableException,
    InvalidLockerTypeException)
from src.exceptions.user_exceptions import (
    UserNotAuthorizedException, UserHasActiveSessionException)
from src.exceptions.payment_exceptions import InvalidPaymentMethodException
from src.exceptions.task_exceptions import TaskNotFoundException


async def get_details(session_id: ObjId, _user: User) -> Optional[SessionView]:
    """Get the details of a session."""
    session: Session = Session(await SessionModel.get(session_id))
    if not session.exists:
        raise SessionNotFoundException(session_id=session_id)

    # TODO: FIXME
    # await session.fetch_link(SessionModel.user)
    # if session.user.id != user.id:
    return await session.view


async def get_session_history(session_id: ObjId, user: User) -> Optional[List[ActionModel]]:
    """Get all actions of a session."""
    session: Session = Session(await SessionModel.get(session_id))
    if not session.exists:
        raise SessionNotFoundException(session_id=session_id)
    if session.user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)

    return await ActionModel.find(
        ActionModel.assigned_session == session_id
    )


async def handle_creation_request(
    user: User,
    callsign: str,
    locker_type: str
) -> Optional[SessionView]:
    """Create a locker session for the user
    at the given station matching the requested locker type."""
    # 1: Find the station and confirm its availability
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none()
    )
    if not station.exists:
        raise StationNotFoundException(station_id=callsign)
    if not await station.is_available:
        raise StationNotAvailableException(callsign=callsign)

    # 2: Check whether the user exists and is authorized to create a session
    if await user.has_active_session:
        raise UserHasActiveSessionException(user_id=user.id)
    if await user.get_expired_session_count(timedelta(days=1)) > 2:
        raise UserNotAuthorizedException(user_id=user.id)

    # 5: Check whether the given locker type exists
    if locker_type.lower() not in LOCKER_TYPES.keys():
        raise InvalidLockerTypeException(locker_type=locker_type)
    locker_type = LOCKER_TYPES[locker_type]

    # 6: Try to claim a locker at this station
    locker: Locker = await Locker().find_available(
        station=station, locker_type=locker_type)
    if not locker.exists:
        raise LockerNotAvailableException(station_callsign=callsign)

    # 7: Create a new session
    session = Session(await SessionModel(
        user=user.doc,
        assigned_station=station.doc,
        assigned_locker=locker.doc,
    ).insert())

    # 8: Await user to select payment method
    task: Task = Task(await TaskItemModel(
        target=TaskTarget.USER,
        task_type=TaskType.REPORT,
        assigned_session=session.doc,
        assigned_station=station.doc,
        timeout_states=[SessionState.EXPIRED],
        moves_session=False
    ).insert())
    await task.move_in_queue()

    # 8: Log the action
    await create_action(session.id, SessionState.CREATED)

    return await session.view


async def handle_payment_selection(
    session_id: ObjId,
    user: User,
    payment_method: str
) -> Optional[SessionView]:
    """Assign a payment method to a session."""
    # 1: Check if payment method is available
    payment_method: str = payment_method.lower()
    if payment_method not in PaymentTypes:
        raise InvalidPaymentMethodException(
            session_id=session_id,
            payment_method=payment_method)

    # 2: Find the related task
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
            assigned_station=None,  # TODO: Improve
            raise_http=False)

    # 3: Fetch the assigned session and verify its state
    await task.doc.fetch_all_links()
    session: Session = Session(task.assigned_session)
    assert (session.exists
            ), f"Could not find session '#{session_id}' for task '#{task.id}'"
    if session.user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)
    if session.session_state != SessionState.CREATED:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionState.CREATED],
            actual_state=session.session_state)

    # 4: Assign the payment method to the session
    session.payment_method = payment_method
    logger.debug(
        (f"Payment method '{payment_method.upper()}' "
         f"assigned to session '#{session.id}'.")
    )
    session.doc.session_state = SessionState.PAYMENT_SELECTED
    await session.doc.save_changes()

    # 5: Await the user to request payment
    await Task(await TaskItemModel(
        target=TaskTarget.USER,
        task_type=TaskType.REPORT,
        assigned_session=session.doc,
        assigned_station=session.assigned_station,
        timeout_states=[SessionState.EXPIRED],
        moves_session=False
    ).insert()).move_in_queue()

    # 6: Complete task and send update
    # Important: This must be send after the new task has been created
    # in order to deal with rapid requests
    await session.doc.save_changes()
    await task.complete()

    return await session.view


async def handle_verification_request(
    session_id: ObjId,
    user: User
) -> Optional[SessionView]:
    """Enter the verification queue of a session."""
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
    await session.doc.sync()
    assert (session.exists
            ), f"Could not find session '#{session_id}' for task '#{task.id}'"
    if session.user.id != user.id:
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
        assigned_session=session.doc,
        assigned_station=session.assigned_station,
        timeout_states=[SessionState.ABORTED],
        moves_session=False
    ).insert()).move_in_queue()

    await create_action(session.id, SessionState.VERIFICATION)
    return await session.view


async def handle_hold_request(session_id: ObjId, user: User) -> Optional[SessionView]:
    """Pause an active session if authorized to do so.
    This is only possible when the payment method is a digital one for safety reasons.
    """
    # 1: Find the session and check whether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id))
    await session.doc.fetch_link(SessionModel.user)
    if session.user.id != user.id:
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

    await create_action(session.id, SessionState.HOLD)

    return await session.view


async def handle_payment_request(session_id: ObjId, user: User) -> Optional[SessionView]:
    """Put the station into payment mode"""
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

    # 2: Get the assigned session and station
    await task.doc.fetch_all_links()
    session: Session = Session(task.assigned_session)
    station: Station = Station(task.assigned_station)

    if not task.exists:
        raise TaskNotFoundException(
            task_type=TaskType.REPORT,
            assigned_station=station.id,
            raise_http=False)

    #  3: Set the task to completed
    task.doc.task_state = TaskState.COMPLETED

    # 3: Validate session result
    if session.user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)

    ACCEPTED_STATES = [SessionState.ACTIVE,  # pylint: disable=invalid-name
                       SessionState.HOLD]
    if session.session_state not in ACCEPTED_STATES:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=ACCEPTED_STATES,
            actual_state=session.session_state)

    # 4: Create a payment object
    await task.doc.save_changes()
    await Payment().create(session=session.doc)

    # 5: Await station to enable terminal
    await Task(await TaskItemModel(
        target=TaskTarget.TERMINAL,
        task_type=TaskType.CONFIRMATION,
        assigned_session=session.doc,
        assigned_station=session.assigned_station,
        timeout_states=[session.session_state,
                        SessionState.EXPIRED],
        moves_session=False,
    ).insert()).move_in_queue()

    # 6: Log the request
    await create_action(session.id, SessionState.PAYMENT)

    return await session.view


async def handle_cancel_request(session_id: ObjId, user: User) -> Optional[SessionView]:
    """Cancel a session before it has been started
    :param session_id: The ID of the assigned session
    :param user_id: used for auth (depreceated)
    :returns: A View of the modified session
    """
    # 1: Find the session and check whether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id))
    if not session.exists:
        raise SessionNotFoundException(session_id=session_id)

    await session.doc.fetch_link(SessionModel.user)
    if str(session.user) != user.id:
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

    # 6. If all checks passed, set session to canceled
    session.doc.session_state = SessionState.CANCELLED
    await create_action(session.id, SessionState.CANCELLED)

    # 7. Save changes
    await session.doc.save_changes()

    return session


async def handle_update_subscription_request(session_id: ObjId, socket: WebSocket):
    """Process a user request to get updates for a session."""
    # 1: Check whether the session exists
    session: Session = Session(await SessionModel.get(session_id))
    if not session.exists:
        # Close the WebSocket connection with a normal closure code
        await socket.close(code=1000)
        raise SessionNotFoundException(session_id=session_id)

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
    logger.debug(
        ("Subscription has been ACTIVATED for "
         f"session '#{session.id}'."))
    await socket.send_text(session.session_state)
    try:
        while True:
            await socket.receive_bytes()

    # 5: Register a disconnect event
    except WebSocketDisconnect:
        logger.debug(
            ("Subscription has been DEACTIVATED for "
             f"session '#{session.id}' at station."))
        websocket_services.unregister_connection(session.id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error in ws for session '#{
                     session.id}': {e}")
        # Close the WebSocket connection with an internal error code
        await socket.close(code=1011)
        websocket_services.unregister_connection(session.id)
