"""Provides utility functions for the sesssion management backend."""

# Basics
from datetime import datetime, timedelta

# Typing
from typing import List, Optional
from uuid import UUID

# ObjectID handling
from beanie import PydanticObjectId as ObjId

# FastAPI utilities
from fastapi import HTTPException, WebSocket, WebSocketDisconnect

# Entities
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.task_entity import Task, TaskTypes, TaskStates
from src.entities.locker_entity import Locker
from src.entities.payment_entity import Payment

# Models
from src.models.session_models import PaymentTypes
from src.models.session_models import (
    SessionModel,
    SessionView,
    SessionStates,
)

from src.models.action_models import ActionModel


# Services
from src.services.action_services import create_action
from src.services.locker_services import LOCKER_TYPES
from src.services.logging_services import logger
from src.services import websocket_services
from src.services.exceptions import ServiceExceptions


async def get_details(session_id: ObjId, user_id: UUID) -> Optional[SessionView]:
    """Get the details of a session."""
    session: Session = await Session().find(session_id=session_id)
    await session.fetch_links()
    if str(session.user) != user_id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)
    return await session.view


async def get_session_history(session_id: ObjId, user_id: UUID) -> Optional[List[ActionModel]]:
    """Get all actions of a session."""
    session: Session = await Session().find(session_id=session_id)
    if str(session.user) != user_id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    return await ActionModel.find(
        ActionModel.assigned_session == session_id
    )


async def handle_creation_request(
    user_id: UUID, callsign: str, locker_type: str
) -> Optional[SessionView]:
    """Create a locker session for the user
    at the given station matching the requested locker type."""
    # 1: Check if the station exists
    station: Station = await Station.find(call_sign=callsign)
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND, station=callsign)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.STATION_NOT_FOUND.value
        )

    # 2: Check if the station is available
    if not await station.is_available:
        # Check whether the station is available
        logger.info(ServiceExceptions.STATION_NOT_AVAILABLE, station=callsign)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.STATION_NOT_AVAILABLE.value
        )

    # 3: Check if the user already has a running session
    session: Session = await Session().find(user_id=user_id, session_active=True)
    if session.exists:
        logger.info(ServiceExceptions.USER_HAS_ACTIVE_SESSION, user=user_id)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.USER_HAS_ACTIVE_SESSION.value
        )

    # 4: Check whether the user has had too many expired sessions recently
    expired_session_count = await SessionModel.find(
        SessionModel.user.id == user_id,  # pylint: disable=no-member
        SessionModel.session_state == SessionStates.EXPIRED,
        SessionModel.created_ts >= (datetime.now() - timedelta(hours=24)),
        fetch_links=True
    ).count()
    if expired_session_count > 1:  # TODO: Add handler here
        logger.info(ServiceExceptions.LIMIT_EXCEEDED, user=user_id)
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
        user_id=user_id,
        locker=locker.document,
        station=station.document)
    logger.debug(
        f"Created session '{session.id}' at locker '{locker.id}'."
    )

    # 8: Await user to select payment method
    await Task().create(
        task_type=TaskTypes.USER,
        station=station.document,
        session=session.document,
        queued_state=None,
        timeout_states=[SessionStates.EXPIRED],
        has_queue=False
    )

    # 8: Log the action
    await create_action(session.id, SessionStates.CREATED)

    return await session.view


async def handle_payment_selection(
    session_id: ObjId, user_id: UUID, payment_method: str
) -> Optional[SessionView]:
    """Assign a payment method to a session."""
    # 1: Check if payment method is available
    payment_method: str = payment_method.lower()
    if payment_method not in PaymentTypes:
        logger.info(
            ServiceExceptions.PAYMENT_METHOD_NOT_SUPPORTED,
            session=session_id,
            detail=payment_method,
        )
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.PAYMENT_METHOD_NOT_SUPPORTED.value
        )

    # 2: Check if the session exists
    session: Session = await Session().find(session_id=session_id)
    await session.fetch_links()
    if str(session.user) != user_id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session.id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 3: Find the related task
    task: Task = await Task().find(
        assigned_session=session.id,
        task_type=TaskTypes.USER,
        task_state=TaskStates.PENDING)
    await task.set_state(TaskStates.COMPLETED)

    # 4: Check if the session is in the correct state
    if session.session_state != SessionStates.CREATED:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.name)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )

    # 5: Assign the payment method to the session
    await session.assign_payment_method(payment_method)
    await session.set_state(SessionStates.PAYMENT_SELECTED, notify=False)

    return await session.view


async def handle_verification_request(
    session_id: ObjId,
    user_id: UUID
) -> Optional[SessionView]:
    """Enter the verification queue of a session."""
    # 1: Find the related session
    session: Session = await Session().find(session_id=session_id)
    await session.fetch_links()
    # TODO: Maybe we can write a custom AssertException handler that takes the ServiceException and creates a HTTPException
    if str(session.user) != user_id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 2: Check if the session is in the correct states
    if session.session_state != SessionStates.PAYMENT_SELECTED:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.name)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )

    # 3: Find the station
    if not session.assigned_station:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND,
                    session=session.assigned_station)
        raise HTTPException(
            status_code=500, detail=ServiceExceptions.STATION_NOT_FOUND.value
        )

    # 5: Await station to enable terminal
    await session.document.fetch_all_links()
    await Task().create(
        task_type=TaskTypes.TERMINAL,
        station=session.assigned_station,
        session=session.document,
        queued_state=SessionStates.VERIFICATION,
        timeout_states=[SessionStates.ABORTED],
        has_queue=True
    )

    # 6: Log a queueVerification action
    await create_action(session.id, SessionStates.VERIFICATION)

    return await session.view


async def handle_hold_request(session_id: ObjId, user_id: UUID) -> Optional[SessionView]:
    """Pause an active session if authorized to do so.
    This is only possible when the payment method is a digital one for safety reasons.
    """
    # 1: Find the session and check whether it belongs to the user
    session: Session = await Session().find(session_id=session_id)
    await session.fetch_links()
    if str(session.user) != user_id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 2: Check whether the session is active
    if session.session_state != SessionStates.ACTIVE:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.name)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )
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
        logger.info(ServiceExceptions.LOCKER_NOT_FOUND, session=session.id)

    await create_action(session.id, SessionStates.HOLD)

    return await session.view


async def handle_payment_request(session_id: ObjId, user_id: UUID) -> Optional[SessionView]:
    """Put the station into payment mode"""
    # 1: Find the session and check whether it belongs to the user
    session: Session = await Session().find(session_id=session_id)
    await session.fetch_links()
    if str(session.user) != user_id:
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
        task_type=TaskTypes.TERMINAL,
        station=session.assigned_station,
        session=session.document,
        queued_state=SessionStates.PAYMENT,
        timeout_states=[session.session_state,
                        SessionStates.EXPIRED],
        has_queue=True
    )

    # 6: Log the request
    await create_action(session.id, SessionStates.PAYMENT)

    return await session.view


async def handle_cancel_request(session_id: ObjId, user_id: UUID) -> Optional[SessionView]:
    """Cancel a session before it has been started
    :param session_id: The ID of the assigned session
    :param user_id: used for auth (depreceated)
    :returns: A View of the modified session
    """
    # 1: Find the session and check whether it belongs to the user
    session: Session = await Session().find(session_id=session_id)
    await session.fetch_links()
    if str(session.user) != user_id:
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

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

    # If all checks passed, set session to canceled
    await session.set_state(SessionStates.CANCELLED)

    # Log a cancelSession action
    await create_action(session.id, SessionStates.CANCELLED)

    return session


async def handle_update_subscription_request(session_id: ObjId, socket: WebSocket):
    """Process a user request to get updates for a session."""
    # 1: Check whether the session exists
    session: Session = await Session().find(session_id=session_id)
    if not session.exists:
        return

    # 2: Check whether the websocket connection already exists
    if websocket_services.get_connection(session.id):
        logger.debug(
            f"Session '{session.id}' cannot have more than one update subscription.")
        return

    # 3: Check if the session is not in an inactive state
    if not session.session_state['is_active']:
        logger.debug(
            f"Session '{session.id}' is not offering updates anymore.")
        return

    # 3: Register the connection
    await socket.accept()
    websocket_services.register_connection(session.id, socket)
    logger.debug(f"Session '{session.id}' is now sending updates.")
    try:
        await socket.receive_bytes()

    # 4: Register a disconnect event
    except WebSocketDisconnect:
        logger.debug(f"Session '{session.id}' is no longer sending updates.")
