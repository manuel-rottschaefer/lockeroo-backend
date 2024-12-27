"""
    This module contains the FastAPI router for handling requests related sessions.
"""
# Basics
from typing import Annotated, List, Optional

# Database utils
from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import APIRouter, Depends, Header, Path, Query, WebSocket, status

# Entities
from src.entities.user_entity import User
from src.models.action_models import ActionView
# from fief_client import FiefAccessTokenInfo
# Models
from src.models.session_models import PaymentTypes, SessionView
# Services
from src.services import session_services
from src.services.auth_services import require_auth
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger

# Create the router
session_router = APIRouter()


### REST ENDPOINTS ###


@session_router.get(
    '/{session_id}/details',
    response_model=Optional[SessionView],
    status_code=status.HTTP_200_OK,
    description=('Get the details of a session including (active) time,'
                 'current price and locker state.')
)
@ handle_exceptions(logger)
async def get_session_details(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    _user: str = Header(default=None, alias="user"),
    access_info: User = Depends(require_auth),
):
    """Return the details of a session. This is supposed to be used
    for refreshingthe app-state in case of disconnect or re-open."""
    logger.info(f"User '#{access_info.fief_id}' is requesting details for session '#{
                session_id}'.")
    return await session_services.get_details(
        session_id=ObjId(session_id),
        user=access_info
    )


@session_router.post(
    '/create',
    response_model=Optional[SessionView],
    status_code=status.HTTP_201_CREATED,
    description='Request a new session at a given station')
async def request_new_session(
    station_callsign: Annotated[str, Query(pattern='^[A-Z]{6}$')],
    locker_type: str,

    _user: str = Header(default=None, alias="user"),
    access_info: User = Depends(require_auth),
):
    """Handle request to create a new session"""
    logger.info((f"User '#{access_info.fief_id}' is requesting a "
                f"new session at station '{station_callsign}'."))
    return await session_services.handle_creation_request(
        user=access_info,
        callsign=station_callsign,
        locker_type=locker_type
    )


@ session_router.put(
    '/{sessionID}/cancel',
    response_model=Optional[SessionView],
    status_code=status.HTTP_200_OK,
    description='Request to cancel a locker session before it has been started')
async def request_session_cancel(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],

    _user: str = Header(default=None, alias="user"),
    access_info: User = Depends(require_auth),
):
    """Handle request to cancel a locker session"""

    logger.info((f"User '#{access_info.id}' is trying to "
                f"cancel session '#{session_id}'."))
    return await session_services.handle_cancel_request(
        session_id=session_id,
        user=access_info
    )


@ session_router.put(
    '/{session_id}/payment/select',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description="Select a payment method for a session")
@ handle_exceptions(logger)
async def choose_session_payment_method(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    payment_method: PaymentTypes,
    _user: str = Header(default=None, alias="user"),
    access_info: User = Depends(require_auth),
):
    """Handle request to select a payment method"""
    logger.info((f"User '#{access_info.id}' is choosing a "
                f"payment method for session '#{session_id}'."))
    return await session_services.handle_payment_selection(
        user=access_info,
        session_id=ObjId(session_id),
        payment_method=payment_method
    )


@ session_router.put(
    '/{session_id}/payment/verify',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Request to enter the verification queue of a session')
@ handle_exceptions(logger)
async def request_session_verification(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],

    _user: str = Header(default=None, alias="user"),
    access_info: User = Depends(require_auth),
):
    """Handle request to enter the verification queue of a session"""
    logger.info(
        (f"User '#{access_info.id}' is requesting to conduct a "
         f"verification for session '#{session_id}'."))
    return await session_services.handle_verification_request(
        session_id=ObjId(session_id),
        user=access_info)


@ session_router.put(
    '/{session_id}/hold',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Request to hold (pause) a locker session')
@ handle_exceptions(logger)
async def request_session_hold(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],

    _user: str = Header(default=None, alias="user"),
    access_info: User = Depends(require_auth),
):
    """Handle request to pause a locker session"""
    logger.info(
        (f"User '#{access_info.id}' is trying to "
         f"hold session '#{session_id}'."))
    return await session_services.handle_hold_request(
        session_id=ObjId(session_id),
        user=access_info
    )


@ session_router.put(
    '/{session_id}/payment',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Request to enter the payment phase of a session')
@ handle_exceptions(logger)
async def request_session_payment(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],

    _user: str = Header(default=None, alias="user"),
    access_info: User = Depends(require_auth),
):
    """Handle request to enter the payment phase of a session"""
    logger.info(
        (f"User '#{access_info.id}' is requesting to "
         f"conduct a payment for session '#{session_id}'."))
    return await session_services.handle_payment_request(
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
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    _user: str = Header(default=None, alias="user"),
    access_info: User = Depends(require_auth),
):
    """Handle request to obtain a list of all actions from a session."""
    return await session_services.get_session_history(
        session_id=session_id,
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
