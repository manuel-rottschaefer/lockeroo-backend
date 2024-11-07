'''This module handles all session related services.'''

# Basics
import asyncio
import os

# Environment
from dotenv import load_dotenv

# ObjectID handling
from beanie import PydanticObjectId as ObjId

# FastAPI utilities
from fastapi import HTTPException

# Entities
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.queue_entity import QueueItem
from src.entities.locker_entity import Locker

# Models
from src.models.session_models import (
    SessionView,
    SessionModel,
    SessionPaymentTypes,
    SessionStates,
)
from src.models.station_models import StationStates

# Services
from .users_services import has_active_session
from .action_services import create_action
from .logging_services import logger
from .exceptions import ServiceExceptions


async def get_details(session_id: ObjId) -> SessionView:
    '''Get the details of a session'''
    session: Session = await Session(SessionModel.get(session_id))
    if not session:
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.SESSION_NOT_FOUND.value
        )

    return session


async def handle_creation_request(
    user_id: ObjId, callsign: str, locker_type: str
) -> SessionView:
    '''Create a locker session for the user
    at the given station matching the requested locker type'''
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
    # TODO: Get this from the session site.
    if await has_active_session(user_id):
        logger.info(ServiceExceptions.USER_HAS_ACTIVE_SESSION, user=user_id)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.USER_HAS_ACTIVE_SESSION.value
        )

    # TODO: 5: Check wether the user has had more than 2 expired session in the last 12 hours.

    # 5: Try to claim a locker at this station
    locker: Locker = Locker(await station.find_available_locker(locker_type))
    if not locker:
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.LOCKER_NOT_AVAILABLE.value
        )

    # 6: Create a new session
    session: Session = await Session.fetch(user_id=user_id,
                                           locker_id=locker.id,
                                           station_id=station.id)

    # 7: Log the action
    await create_action(session.id, SessionStates.CREATED)

    # Convert to activeSession object and assign locker index
    new_session: SessionView = SessionView.model_validate(session.document)
    # TODO: Integrate this into the main session object?
    new_session.locker_index = locker.station_index

    return new_session


async def handle_payment_selection(
    session_id: ObjId, _user_id: ObjId, payment_method: str
) -> SessionView:
    '''Assign a payment method to a session'''
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
    session: Session = await Session.fetch(session_id=session_id)
    if not session:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND, session=session_id)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.SESSION_NOT_FOUND.value
        )

    # 3: Check if the session is in the correct state
    if session.session_state != SessionStates.CREATED:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.value)
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )

    # 4: Assign the payment method to the session
    await session.assign_payment_method(payment_method)
    # TODO: No session state broadcasting here
    await session.set_state(SessionStates.PAYMENT_SELECTED, notify=False)

    return session


async def handle_verification_request(
    session_id: ObjId, _user_id: ObjId
) -> SessionView:
    '''Enter the verification queue of a session'''
    # 1: Find the session
    session: Session = await Session.fetch(session_id=session_id)
    if not session:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND, session=session_id)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.SESSION_NOT_FOUND.value
        )

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

    # 4: If all checks pass, set the session to verification queued
    await session.set_state(SessionStates.VERIFICATION_QUEUED, notify=False)

    # 5: Create a queue item at this station
    queue: QueueItem = await QueueItem().create(station.id, session.id)
    # Wait 120 seconds until the session expires
    asyncio.create_task(queue.register_expiration(
        os.getenv('VERIFICATION_EXPIRATION'), SessionStates.PAYMENT_SELECTED))

    # 6: Log a queueVerification action
    await create_action(session.id, SessionStates.VERIFICATION_QUEUED)

    return session


async def handle_hold_request(session_id: ObjId, _user_id: ObjId) -> SessionView:
    '''Pause an active session if authorized to do so.
    This is only possible when the payment method is a digital one for safety reasons.
    '''
    # 1: Get the session
    session: Session = Session(await SessionModel.get(session_id))
    if not session.exists:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND, session=session_id)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.STATION_NOT_FOUND.value
        )
    print(session.session_state)

    # 2: Check wether the session is active
    if session.session_state != SessionStates.ACTIVE:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session_id, detail=session.session_state.value)
        print('raising')
        raise HTTPException(
            status_code=400, detail=ServiceExceptions.WRONG_SESSION_STATE.value
        )
    print(session.payment_method)
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


async def handle_payment_request(session_id: ObjId, _user_id: ObjId) -> SessionView:
    '''Put the station into payment mode'''
    # 1: Find the session
    session: Session = await Session().fetch(session_id=session_id)
    if not session:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND, session=session_id)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.SESSION_NOT_FOUND.value
        )

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

    # 4: If all checks pass, set the session to verification queued
    await session.set_state(SessionStates.PAYMENT_QUEUED)

    # 5: Create a queue item and execute if it is next in the queue
    queue: QueueItem = await QueueItem().create(station.id, session.id)
    # Wait 120 seconds until the session expires
    asyncio.create_task(queue.register_expiration(
        os.getenv('PAYMENT_EXPIRATON'), SessionStates.ACTIVE))

    # 6: Log the request
    await create_action(session.id, SessionStates.PAYMENT_QUEUED)

    return session


async def handle_cancel_request(session_id: ObjId, _user_id: ObjId) -> SessionView:
    '''Cancel a session before it has been started
    :param session_id: The ID of the assigned session
    :param user_id: used for auth (depreceated)
    :returns: A View of the modified session
    '''
    # Get the related session
    session: Session = await Session.fetch(session_id=session_id)
    if not session:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND, session=session_id)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.SESSION_NOT_FOUND.value
        )

    accepted_states: list = [
        SessionStates.CREATED,
        SessionStates.PAYMENT_SELECTED,
        SessionStates.VERIFICATION_QUEUED,
        SessionStates.VERIFICATION_PENDING,
        SessionStates.STASHING,
    ]
    # TODO: The session can only be canceled if the locker is also closed
    # We need a system to store the next desired session state after the locker has been closed
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
