"""
Lockeroo.session_router
-------------------------
This module provides endpoint routing for session functionalities

Key Features:
    - Provides various session endpoints

Dependencies:
    - fastapi
    - beanie
"""
# Basics
from typing import Annotated, List, Optional
from bson.objectid import ObjectId
from asyncio import Lock
# FastAPI & Beanie
from fastapi import APIRouter, Response, Depends, Path, Query, WebSocket, status
from beanie import PydanticObjectId as ObjId
# Entities
from src.entities.user_entity import User
# Models
from lockeroo_models.station_models import PaymentMethod
from lockeroo_models.snapshot_models import SnapshotModel
from lockeroo_models.session_models import (
    SessionView,
    SessionBillView,
    SessionConcludedView)
# Services
from src.services import session_services
from src.services.locker_services import LOCKER_TYPE_NAMES
from src.services.auth_services import auth_check
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger_service as logger

# Create the router
session_router = APIRouter()


### REST ENDPOINTS ###


@session_router.get(
    '/{session_id}/',
    response_model=Optional[SessionView],
    status_code=status.HTTP_200_OK,
    description=('Get the details of a session including (active) time,'
                 'current price and locker state.')
)
@handle_exceptions(logger)
async def get_session_details(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
):
    """Return the details of a session. This is supposed to be used
    for refreshingthe app-state in case of disconnect or re-open."""
    logger.info(
        (f"User '{user.doc.fief_id}' is requesting "
         f"details for session '#{session_id}'."), session_id=session_id)
    return await session_services.get_details(
        user=user,
        session_id=ObjId(session_id))


@session_router.get(
    '/{session_id}/history',
    response_model=Optional[List[SnapshotModel]],
    status_code=status.HTTP_200_OK,
    description="Get a list of all actions of a session.")
@handle_exceptions(logger)
async def get_session_history(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
):
    """Handle request to obtain a list of all actions from a session."""
    return await session_services.get_session_history(
        user=user,
        session_id=session_id)


@session_router.post(
    '/create',
    response_model=Optional[SessionView],
    status_code=status.HTTP_201_CREATED,
    description='Request a new session at a given station')
@handle_exceptions(logger)
async def request_new_session(
    response: Response,
    station_callsign: Annotated[str, Query(
        pattern='^[A-Z]{6}$',
        example="MUCODE",
        description='Callsign of the station.')],
    locker_type: Annotated[str, Query(
        enum=LOCKER_TYPE_NAMES,
        description='Type of locker to be used.')],
    payment_method: Annotated[PaymentMethod, Query(
        example=PaymentMethod.TERMINAL,
        description='Payment method to be used.')] = None,
    user: User = Depends(auth_check),
) -> Optional[SessionView]:
    """Handle request to create a new session"""
    logger.info((f"User '{user.fief_id}' is requesting a "
                f"new session at station '{station_callsign}'."))
    async with Lock():  # TODO: Check if lock solves the problem adequately
        return await session_services.handle_creation_request(
            user=user,
            callsign=station_callsign,
            locker_type=locker_type,
            payment_method=payment_method,
            response=response)


@session_router.patch(
    '/{session_id}/cancel',
    response_model=Optional[SessionConcludedView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Request to cancel a locker session before it has been started')
@handle_exceptions(logger)
async def request_session_cancel(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
) -> Optional[SessionConcludedView]:
    """Handle request to cancel a locker session"""
    logger.info((f"User '{user.fief_id}' is trying to "
                f"cancel session '#{session_id}'."), session_id=session_id)
    return await session_services.handle_cancel_request(
        user=user,
        session_id=ObjId(session_id))


@session_router.patch(
    '/{session_id}/hold',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Request to hold (pause) a locker session')
@handle_exceptions(logger)
async def request_session_hold(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
):
    """Handle request to pause a locker session"""
    logger.info(
        (f"User '{user.fief_id}' is trying to "
         f"hold the session."), session_id=session_id)
    return await session_services.handle_hold_request(
        user=user,
        session_id=ObjId(session_id))


@session_router.get(
    '/{session_id}/bill',
    response_model=SessionBillView,
    status_code=status.HTTP_200_OK,
    description='Get the bill of a session')
@handle_exceptions(logger)
async def get_session_bill(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
):
    """Handle request to get the bill of a session"""

    return await session_services.get_session_bill(
        user=user,
        session_id=ObjId(session_id))


@session_router.websocket('/subscribe')
async def subscribe_to_session(
        socket: WebSocket):
    """Handle subscription to a session update flow."""
    await session_services.handle_update_subscription_request(
        socket=socket)
