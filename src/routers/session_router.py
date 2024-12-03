"""
    This module contains the FastAPI router for handling requests related sessions.
"""
# Basics
from typing import List, Annotated, Optional

# Database utils
from beanie import PydanticObjectId as ObjId

# FastAPI
from fastapi import APIRouter, WebSocket, Path, Query
from fief_client import FiefAccessTokenInfo

# Models
from src.models.session_models import PaymentTypes
from src.models.session_models import SessionView
from src.models.action_models import ActionView

# Services
from src.services import session_services
from src.services.exceptions import handle_exceptions
from src.services.logging_services import logger
from src.services.auth_services import require_auth

# Create the router
session_router = APIRouter()


### REST ENDPOINTS ###

@session_router.get('/{session_id}/details',
                    response_model=Optional[SessionView],
                    description=('Get the details of a session including (active) time,'
                                 'current price and locker state.')
                    )
@handle_exceptions(logger)
@require_auth
async def get_session_details(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    access_info: FiefAccessTokenInfo = None
):
    """Return the details of a session. This is supposed to be used
    for refreshingthe app-state in case of disconnect or re-open."""
    return await session_services.get_details(
        session_id=ObjId(session_id),
        account_id=access_info['id']
    )


@session_router.post('/create',
                     response_model=Optional[SessionView],
                     description='Request a new session at a given station')
@require_auth
async def request_new_session(
    station_callsign: Annotated[str, Query(pattern='^[A-Z]{6}$')],
    locker_type: str,
    access_info: FiefAccessTokenInfo = None,
    account_id: str = None
):
    """Handle request to create a new session"""
    return await session_services.handle_creation_request(
        account_id=access_info['id'],
        callsign=station_callsign,
        locker_type=locker_type
    )


@ session_router.put('/{sessionID}/cancel',
                     response_model=Optional[SessionView],
                     description='Request to cancel a locker session before it has been started')
@require_auth
async def request_session_cancel(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    access_info: FiefAccessTokenInfo = None,
    account_id: str = None
):
    """Handle request to cancel a locker session"""
    return await session_services.handle_cancel_request(
        session_id=session_id,
        account_id=access_info['id']
    )


@ session_router.put('/{session_id}/payment/select',
                     response_model=Optional[SessionView],
                     description="Select a payment method for a session")
@ handle_exceptions(logger)
@require_auth
async def choose_session_payment_method(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    payment_method: PaymentTypes,
    access_info: FiefAccessTokenInfo = None,
    account_id: str = None
):
    """Handle request to select a payment method"""
    return await session_services.handle_payment_selection(
        session_id=ObjId(session_id),
        account_id=access_info['id'],
        payment_method=payment_method
    )


@ session_router.put('/{session_id}/payment/verify',
                     response_model=Optional[SessionView],
                     description='Request to enter the verification queue of a session')
@ handle_exceptions(logger)
@require_auth
async def request_session_verification(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    access_info: FiefAccessTokenInfo = None,
    account_id: str = None
):
    """Handle request to enter the verification queue of a session"""
    return await session_services.handle_verification_request(
        session_id=ObjId(session_id),
        account_id=access_info['id'])


@ session_router.put('/{session_id}/hold',
                     response_model=Optional[SessionView],
                     description='Request to hold (pause) a locker session')
@ handle_exceptions(logger)
@require_auth
async def request_session_hold(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    access_info: FiefAccessTokenInfo = None,
):
    """Handle request to pause a locker session"""
    return await session_services.handle_hold_request(
        session_id=ObjId(session_id),
        account_id=access_info['id']
    )


@ session_router.put('/{session_id}/payment',
                     response_model=Optional[SessionView],
                     description='Request to enter the payment phase of a session')
@ handle_exceptions(logger)
@require_auth
async def request_session_payment(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    access_info: FiefAccessTokenInfo = None,
):
    """Handle request to enter the payment phase of a session"""
    return await session_services.handle_payment_request(
        session_id=ObjId(session_id),
        account_id=access_info['id']
    )


@ session_router.get('/{session_id}/history',
                     response_model=Optional[List[ActionView]],
                     description="Get a list of all actions of a session.")
@ handle_exceptions(logger)
@require_auth
async def get_session_history(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    access_info: FiefAccessTokenInfo = None,
):
    """Handle request to obtain a list of all actions from a session."""
    return await session_services.get_session_history(
        session_id=session_id,
        account_id=access_info['id']
    )


@session_router.websocket('/{session_id}/subscribe')
async def subscribe_to_session(socket: WebSocket, session_id: str) -> None:
    """Handle subscription to a session update flow."""
    await session_services.handle_update_subscription_request(
        session_id=session_id, socket=socket)
