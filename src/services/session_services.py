"""This module handles all session related services."""

# Typing
from typing import List, Optional
from uuid import UUID

# ObjectID handling
from beanie import PydanticObjectId as ObjId

# FastAPI utilities
from fastapi import HTTPException

# Entities
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.queue_entity import QueueItem
from src.entities.locker_entity import Locker
from src.entities.payment_entity import Payment

# Models
from src.models.session_models import (
    SessionView,
    SessionModel,
    SessionPaymentTypes,
    SessionStates,
)
from src.models.station_models import StationStates
from src.models.action_models import ActionModel

# Services
from .users_services import has_active_session
from .action_services import create_action
from .logging_services import logger
from .exceptions import ServiceExceptions


async def get_details(session_id: ObjId, user_id: UUID) -> Optional[SessionView]:
    """Get the details of a session."""
    session: Session = Session(await SessionModel.get(session_id))
    if str(session.assigned_user) != str(user_id):
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)
    return session


async def get_session_history(session_id: ObjId, user_id: UUID) -> Optional[List[ActionModel]]:
    """Get all actions of a session."""
    session: Session = Session(await SessionModel.get(session_id))
    if str(session.assigned_user) != str(user_id):
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
    # 1: Check if the locker type exists
    if locker_type not in ["small", "medium", "large"]:
        logger.debug("Locker type {locker_type} does not exist.")
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.INVALID_LOCKER_TYPE.value
        )

    # 2: Check if the station exists
    station: Station = await Station.fetch(call_sign=callsign)
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND, station=callsign)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.STATION_NOT_FOUND.value
        )

    # 3: Check if the station is available
    if station.station_state != StationStates.AVAILABLE:
        # Check whether the station is available
        logger.info(ServiceExceptions.STATION_NOT_AVAILABLE, station=callsign)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.STATION_NOT_AVAILABLE.value
        )

    # 4: Check if the user already has a running session
    # TODO: Get this from the session site. Re-implement
    # if await has_active_session(user_id):
    #    logger.info(ServiceExceptions.USER_HAS_ACTIVE_SESSION, user=user_id)
    #    raise HTTPException(
    #        status_code=400, detail=ServiceExceptions.USER_HAS_ACTIVE_SESSION.value
    #    )

    # TODO: 5: Check wether the user has had more than 2 expired session in the last 12 hours.

    # 5: Try to claim a locker at this station
    locker: Locker = Locker(await station.find_available_locker(locker_type))
    if not locker:
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.LOCKER_NOT_AVAILABLE.value
        )

    # 6: Create a new session
    session: Session = await Session.create(user_id=user_id,
                                            locker_id=locker.id,
                                            station_id=station.id)
    logger.debug(
        f"Created session '{session.id}' at locker '{locker.id}'."
    )

    # 7: Log the action
    await create_action(session.id, SessionStates.CREATED)

    # Convert to activeSession object and assign locker index
    new_session: SessionView = SessionView.model_validate(session.document)
    # TODO: Integrate this into the main session object?
    new_session.locker_index = locker.station_index

    return new_session


async def handle_payment_selection(
    session_id: ObjId, user_id: UUID, payment_method: str
) -> Optional[SessionView]:
    """Assign a payment method to a session"""
    # 1: Check if payment method is available
    payment_method: str = payment_method.lower()
    if payment_method not in SessionPaymentTypes:
        logger.info(
            ServiceExceptions.PAYMENT_METHOD_NOT_AVAILABLE,
            session=session_id,
            detail=payment_method,
        )
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.PAYMENT_METHOD_NOT_AVAILABLE.value
        )

    # 2: Check if the session exists
    session: Session = Session(await SessionModel.get(session_id))
    if str(session.assigned_user) != str(user_id):
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 3: Check if the session is in the correct state
    if session.session_state != SessionStates.CREATED:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.value)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )

    # 4: Assign the payment method to the session
    await session.assign_payment_method(payment_method)
    await session.set_state(SessionStates.PAYMENT_SELECTED, notify=False)

    return session


async def handle_verification_request(
    session_id: ObjId,
    user_id: UUID
) -> Optional[SessionView]:
    """Enter the verification queue of a session"""
    # 1: Find the session
    session: Session = Session(await SessionModel.get(session_id))
    if str(session.assigned_user) != str(user_id):
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 2: Check if the session is in the correct states
    if session.session_state not in [SessionStates.PAYMENT_SELECTED]:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.value)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )

    # 3: Find the station
    station: Station = await Station.fetch(station_id=session.assigned_station)
    if not station:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND,
                    session=session.assigned_station)
        raise HTTPException(
            status_code=500, detail=ServiceExceptions.STATION_NOT_FOUND.value
        )

    # 5: Create a queue item at this station
    await QueueItem().create(
        station_id=station.id,
        session_id=session.id,
        next_state=SessionStates.VERIFICATION,
        timeout_state=SessionStates.PAYMENT_SELECTED)

    # 6: Log a queueVerification action
    await create_action(session.id, SessionStates.VERIFICATION)

    return session


async def handle_hold_request(session_id: ObjId, user_id: UUID) -> Optional[SessionView]:
    """Pause an active session if authorized to do so.
    This is only possible when the payment method is a digital one for safety reasons.
    """
    # 1: Find the session and check wether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id))
    if str(session.assigned_user) != str(user_id):
        logger.info(ServiceExceptions.NOT_AUTHORIZED, session=session_id)
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    # 2: Check wether the session is active
    if session.session_state != SessionStates.ACTIVE:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.value)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )
    # 3: Check wether the user has chosen the app method for payment.
    if session.payment_method == SessionPaymentTypes.TERMINAL:
        logger.info(ServiceExceptions.PAYMENT_METHOD_NOT_AVAILABLE,
                    session=session_id)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.PAYMENT_METHOD_NOT_AVAILABLE.value
        )

    # 4: Get the locker and assign an open request
    locker: Locker = await Locker(session.assigned_locker)
    if not locker:
        logger.info(ServiceExceptions.LOCKER_NOT_FOUND, session=session.id)

    await create_action(session.id, SessionStates.HOLD)

    return session


async def handle_payment_request(session_id: ObjId, user_id: UUID) -> Optional[SessionView]:
    """Put the station into payment mode"""
    # 1: Find the session and check wether it belongs to the user
    session: Session = await Session().fetch(session_id=session_id)
    if str(session.assigned_user) != str(user_id):
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
    station: Station = await Station.fetch(station_id=session.assigned_station)
    if not station:
        logger.error(
            f"Station {
                session.assigned_station} not found despite being assigned to a session."
        )
        raise HTTPException(
            status_code=500, detail=ServiceExceptions.STATION_NOT_FOUND.value
        )

    # 5: Create a payment object
    await Payment().create(session_id=session.id)

    # 5: Create a queue item and execute if it is next in the queue
    await QueueItem().create(
        station_id=station.id,
        session_id=session.id,
        next_state=SessionStates.PAYMENT,
        timeout_state=session.session_state
    )

    # 6: Log the request
    await create_action(session.id, SessionStates.PAYMENT)

    return session


async def handle_cancel_request(session_id: ObjId, user_id: UUID) -> Optional[SessionView]:
    """Cancel a session before it has been started
    :param session_id: The ID of the assigned session
    :param user_id: used for auth (depreceated)
    :returns: A View of the modified session
    """
    # 1: Find the session and check wether it belongs to the user
    session: Session = Session(await SessionModel.get(session_id))
    if str(session.assigned_user) != str(user_id):
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
