"""Provides utility functions for the sesssion management backend."""
# Typing
from typing import List, Optional

# ObjectID handling
from beanie import PydanticObjectId as ObjId
# FastAPI utilities
from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from src.entities.locker_entity import Locker
from src.entities.payment_entity import Payment
# Entities
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.task_entity import Task, TaskStates, TaskTypes
# Models
from src.models.action_models import ActionModel
from src.models.session_models import (
    SessionModel, PaymentTypes,
    SessionStates, SessionView,
    ACTIVE_SESSION_STATES)
from src.models.user_models import UserModel
from src.services import websocket_services
# Services
from src.services.user_services import get_expired_session_count
from src.services.action_services import create_action
from src.services.exception_services import ServiceExceptions
from src.services.locker_services import LOCKER_TYPES
from src.services.logging_services import logger
# Exceptions
from src.exceptions.session_exceptions import SessionNotFoundException, InvalidSessionStateException
from src.exceptions.station_exceptions import StationNotFoundException, StationNotAvailableException
from src.exceptions.locker_exceptions import LockerNotFoundException


async def get_details(session_id: ObjId, _user: UserModel) -> Optional[SessionView]:
    """Get the details of a session."""
    session: Session = await Session().find(session_id=session_id)
    if not session.exists:
        raise SessionNotFoundException(session_id=session_id)

    # TODO: FIXME
    # await session.fetch_link(SessionModel.user)
    # if session.user.id != user.id:
    #    logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
    #    raise HTTPException(
    #        status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)
    return await session.view


async def get_session_history(session_id: ObjId, user: UserModel) -> Optional[List[ActionModel]]:
    """Get all actions of a session."""
    session: Session = await Session().find(session_id=session_id)
    if session.user.id != user.id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    return await ActionModel.find(
        ActionModel.assigned_session == session_id
    )


async def handle_creation_request(
    user: UserModel,
    callsign: str,
    locker_type: str
) -> Optional[SessionView]:
    """Create a locker session for the user
    at the given station matching the requested locker type."""
    # 1: Check if the station exists
    station: Station = await Station.find(callsign=callsign)
    if not station.exists:
        raise StationNotFoundException(station_id=callsign)

    # 2: Check if the station is available
    if not await station.is_available:
        raise StationNotAvailableException(callsign=callsign)

    # 3: Check if the user already has a running session
    session: Session = await Session().find(user=user, session_states=ACTIVE_SESSION_STATES)
    if session.exists:
        # logger.info(ServiceExceptions.USER_HAS_ACTIVE_SESSION, user=user.id)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.USER_HAS_ACTIVE_SESSION.value
        )

    # 4: Check whether the user has had too many expired sessions recently
    expired_session_count = await get_expired_session_count(user.id)
    if expired_session_count > 1:  # TODO: Add handler here
        # logger.info(ServiceExceptions.LIMIT_EXCEEDED, user=user.id)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.LIMIT_EXCEEDED.value
        )

    # 5: Check whether the given locker type exists
    if locker_type not in LOCKER_TYPES.keys():
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.INVALID_LOCKER_TYPE
        )
    locker_type = LOCKER_TYPES[locker_type]

    # 6: Try to claim a locker at this station
    locker: Locker = await Locker().find_available(
        station=station, locker_type=locker_type)
    if not locker.exists:
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.LOCKER_NOT_AVAILABLE.value
        )

    # 7: Create a new session
    session: Session = await Session.create(
        user=user,
        locker=locker.document,
        station=station.document)
    logger.debug(
        f"Created session '{session.id}' at locker '{locker.callsign}'."
    )

    # 8: Await user to select payment method
    await Task().create(
        task_type=TaskTypes.USER,
        session=session.document,
        station=station.document,
        queued_state=None,
        timeout_states=[SessionStates.EXPIRED],
        has_queue=False
    )

    # 8: Log the action
    await create_action(session.id, SessionStates.CREATED)

    return await session.view


async def handle_payment_selection(
    session_id: ObjId,
    user: UserModel,
    payment_method: str
) -> Optional[SessionView]:
    """Assign a payment method to a session."""
    # 1: Check if payment method is available
    payment_method: str = payment_method.lower()
    if payment_method not in PaymentTypes:
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.PAYMENT_METHOD_NOT_SUPPORTED.value
        )

    # 2: Check if the session exists
    session: Session = await Session().find(session_id=session_id)
    await session.document.fetch_link(SessionModel.user)
    if session.user.id != user.id:
        # logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session.id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 3: Find the related task
    task: Task = await Task().find(
        task_type=TaskTypes.USER,
        task_state=TaskStates.PENDING,
        assigned_session=session.id,)
    await task.complete()

    # 4: Check if the session is in the correct state
    if session.session_state != SessionStates.CREATED:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_state=SessionStates.CREATED,
            actual_state=session.session_state)

    # 5: Assign the payment method to the session
    await session.assign_payment_method(payment_method)
    session.set_state(SessionStates.PAYMENT_SELECTED)

    # 6: Save changes
    await session.save_model_changes(notify=False)

    return await session.view


async def handle_verification_request(
    session_id: ObjId,
    user: UserModel
) -> Optional[SessionView]:
    """Enter the verification queue of a session."""
    # 1: Find the related session
    session: Session = await Session().find(session_id=session_id)
    if not session.exists:
        raise SessionNotFoundException(session_id=session_id)

    await session.fetch_link(SessionModel.user)
    if session.user.id != user.id:
        # logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 2: Check if the session is in the correct states
    if session.session_state != SessionStates.PAYMENT_SELECTED:
        # logger.info(ServiceExceptions.WRONG_SESSION_STATE,
        #            session=session_id, detail=session.session_state.name)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )

    # 3: Find the station
    if not session.assigned_station:
        raise StationNotFoundException(station_id=session.assigned_station.id)

    # 5: Await station to enable terminal
    await session.document.fetch_link(SessionModel.assigned_station)
    await Task().create(
        task_type=TaskTypes.CONFIRMATION,
        session=session.document,
        station=session.assigned_station,
        queued_state=SessionStates.VERIFICATION,
        timeout_states=[SessionStates.ABORTED],
        has_queue=True
    )

    # 6: Log a queueVerification action
    await create_action(session.id, SessionStates.VERIFICATION)

    return await session.view


async def handle_hold_request(session_id: ObjId, user: UserModel) -> Optional[SessionView]:
    """Pause an active session if authorized to do so.
    This is only possible when the payment method is a digital one for safety reasons.
    """
    # 1: Find the session and check whether it belongs to the user
    session: Session = await Session().find(session_id=session_id)
    await session.fetch_link(SessionModel.user)
    if session.user.id != user.id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 2: Check whether the session is active
    if session.session_state != SessionStates.ACTIVE:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_state=SessionStates.ACTIVE,
            actual_state=session.session_state)

    # 3: Check whether the user has chosen the app method for payment.
    if session.payment_method == PaymentTypes.TERMINAL:
        logger.info(ServiceExceptions.INVALID_PAYMENT_METHOD,
                    session=session_id)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.INVALID_PAYMENT_METHOD.value
        )

    # 4: Get the locker and assign an open request
    locker: Locker = await Locker(session.assigned_locker)
    if not locker:
        raise LockerNotFoundException(locker_id=session.assigned_locker)

    await create_action(session.id, SessionStates.HOLD)

    return await session.view


async def handle_payment_request(session_id: ObjId, user: UserModel) -> Optional[SessionView]:
    """Put the station into payment mode"""
    # 1: Find the session and check whether it belongs to the user
    session: Session = await Session().find(session_id=session_id)
    await session.fetch_link(SessionModel.user)
    if session.user.id != user.id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 2: Check if the session is in the correct state
    if session.session_state not in [SessionStates.ACTIVE, SessionStates.HOLD]:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.value)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )

    # 3: Find the station
    await session.document.fetch_all_links()
    station: Station = Station(session.assigned_station)
    if not station:
        logger.error(
            f"Station {
                session.assigned_station} not found despite being assigned to a session."
        )
        raise HTTPException(
            status_code=500, detail=ServiceExceptions.STATION_NOT_FOUND.value
        )

    # 5: Create a payment object
    await Payment().create(session=session.document)

    # 5: Await station to enable terminal
    await Task().create(
        task_type=TaskTypes.CONFIRMATION,
        session=session.document,
        station=session.assigned_station,
        queued_state=SessionStates.PAYMENT,
        timeout_states=[session.session_state,
                        SessionStates.EXPIRED],
        has_queue=True
    )

    # 6: Log the request
    await create_action(session.id, SessionStates.PAYMENT)

    return await session.view


async def handle_cancel_request(session_id: ObjId, user: UserModel) -> Optional[SessionView]:
    """Cancel a session before it has been started
    :param session_id: The ID of the assigned session
    :param user_id: used for auth (depreceated)
    :returns: A View of the modified session
    """
    # 1: Find the session and check whether it belongs to the user
    session: Session = await Session().find(session_id=session_id)
    if not session.exists:
        raise SessionNotFoundException(session_id=session_id)

    await session.fetch_link(SessionModel.user)
    if str(session.user) != user.id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 2: Check if session is in correct state
    accepted_states: list = [
        SessionStates.CREATED,
        SessionStates.PAYMENT_SELECTED,
        SessionStates.VERIFICATION,
        SessionStates.STASHING,
    ]
    if session.session_state not in accepted_states:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.value)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )

    # 6. If all checks passed, set session to canceled
    session.set_state(SessionStates.CANCELLED)
    await create_action(session.id, SessionStates.CANCELLED)

    # 7. Save changes
    await session.save_model_changes(notify=False)

    return session


async def handle_update_subscription_request(session_id: ObjId, socket: WebSocket):
    """Process a user request to get updates for a session."""
    # 1: Check whether the session exists
    session: Session = await Session().find(session_id=session_id)
    if not session.exists:
        # Close the WebSocket connection with a normal closure code
        await socket.close(code=1000)
        raise SessionNotFoundException(session_id=session_id)

    # 2: Check whether the websocket connection already exists
    if websocket_services.get_connection(session.id):
        logger.debug(
            f"Session '{session.id}' cannot have more than one update subscription.")
        # Close the WebSocket connection with a normal closure code
        await socket.close(code=1000)
        return

    # 3: Check if the session is not in an inactive state
    if session.session_state not in ACTIVE_SESSION_STATES:
        logger.debug(
            f"Session '{session.id}' is not offering updates anymore.")
        # Close the WebSocket connection with a normal closure code
        await socket.close(code=1000)
        return

    # 4: Register the connection
    await socket.accept()
    websocket_services.register_connection(session.id, socket)
    logger.debug(f"Session '{session.id}' is now sending updates.")
    await socket.send_text(session.session_state)
    try:
        while True:
            await socket.receive_bytes()

    # 5: Register a disconnect event
    except WebSocketDisconnect:
        logger.debug(f"Session '{session.id}' is no longer sending updates.")
        websocket_services.unregister_connection(session.id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error in ws for session '{
                     session.id}': {e}")
        # Close the WebSocket connection with an internal error code
        await socket.close(code=1011)
        websocket_services.unregister_connection(session.id)
