"""
    This module contains the FastAPI router for handling requests related sessions.
"""
# Basics
from typing import Annotated, List, Optional
from asyncio import Lock
from uuid import uuid4
# Database utils
from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import APIRouter, Depends, Header, Path, Query, WebSocket, status
# Entities
from src.entities.user_entity import User
from src.models.action_models import ActionView
# from fief_client import FiefAccessTokenInfo
# Models
from src.models.session_models import (
    SessionView,
    CreatedSessionView,
    ConcludedSessionView,
    PaymentMethod)
from src.models.locker_models import LOCKER_TYPE_NAMES
# Services
from src.services import session_services
from src.services.auth_services import require_auth
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
@ handle_exceptions(logger)
async def get_session_details(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example="1234567890abcdef",
        description='Unique identifier of the session.')],
    _user: Annotated[str, Header(
        alias="user", example=uuid4(),
        description="The user who is requesting details about the session.")],
    access_info: User = Depends(require_auth),
):
    """Return the details of a session. This is supposed to be used
    for refreshingthe app-state in case of disconnect or re-open."""
    logger.info(
        (f"User '#{access_info.fief_id}' is requesting "
         f"details for session '#{session_id}'."))
    return await session_services.get_details(
        session_id=ObjId(session_id),
        user=access_info
    )


@ session_router.get(
    '/{session_id}/history',
    response_model=Optional[List[ActionView]],
    status_code=status.HTTP_200_OK,
    description="Get a list of all actions of a session.")
@ handle_exceptions(logger)
async def get_session_history(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example="1234567890abcdef",
        description='Unique identifier of the session.')],
    _user: Annotated[str, Header(
        alias="user", example=uuid4(),
        description="User UUID (only for debug)")],
    access_info: User = Depends(require_auth),
):
    """Handle request to obtain a list of all actions from a session."""
    return await session_services.get_session_history(
        session_id=session_id,
        user=access_info
    )


@session_router.post(
    '/create',
    response_model=Optional[CreatedSessionView],
    status_code=status.HTTP_201_CREATED,
    description='Request a new session at a given station')
async def request_new_session(
    # TODO: Fix the parameters
    # station_callsign: str,
    station_callsign: Annotated[str, Query(
        pattern='^[A-Z]{6}$',
        example="MUCODE",
        description='Callsign of the station.')],
    locker_type: Annotated[str, Query(
        enum=LOCKER_TYPE_NAMES,
        description='Type of locker to be used.')],
    _user: Annotated[str, Header(
        alias="user", example=uuid4(),
        description="The user who is requesting a new session.")],
    payment_method: Annotated[PaymentMethod, Query(
        description='Payment method to be used.')] = None,
    access_info: User = Depends(require_auth),
) -> Optional[CreatedSessionView]:
    """Handle request to create a new session"""
    logger.info((f"User '#{access_info.fief_id}' is requesting a "
                f"new session at station '{station_callsign}'."))
    async with Lock():  # TODO: Check if lock solves the problem adequately
        return await session_services.handle_creation_request(
            user=access_info,
            callsign=station_callsign,
            locker_type=locker_type,
            payment_method=payment_method
        )


@ session_router.patch(
    '/{session_id}/cancel',
    response_model=Optional[ConcludedSessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Request to cancel a locker session before it has been started')
async def request_session_cancel(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example="1234567890abcdef",
        description='Unique identifier of the session.')],
    _user: Annotated[str, Header(
        alias="user", example=uuid4(),
        description="User UUID (only for debug)")],
    access_info: User = Depends(require_auth)
) -> Optional[ConcludedSessionView]:
    """Handle request to cancel a locker session"""
    logger.info((f"User '#{access_info.id}' is trying to "
                f"cancel session '#{session_id}'."))
    return await session_services.handle_cancel_request(
        session_id=ObjId(session_id),
        user=access_info
    )


@ session_router.patch(
    '/{session_id}/hold',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Request to hold (pause) a locker session')
@ handle_exceptions(logger)
async def request_session_hold(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example="1234567890abcdef",
        description='Unique identifier of the session.')],
    _user: Annotated[str, Header(
        alias="user", example=uuid4(),
        description="User UUID (only for debug)")],
    access_info: User = Depends(require_auth)
):
    """Handle request to pause a locker session"""
    logger.info(
        (f"User '#{access_info.id}' is trying to "
         f"hold session '#{session_id}'."))
    return await session_services.handle_hold_request(
        session_id=ObjId(session_id),
        user=access_info
    )


@session_router.websocket('/{session_id}/subscribe')
async def subscribe_to_session(
        socket: WebSocket,
        user_id: str,
        session_token: str,
        session_id: str) -> None:
    """Handle subscription to a session update flow."""
    await session_services.handle_update_subscription_request(
        session_id=session_id,
        session_token=session_token,
        user_id=user_id,
        socket=socket)
