"""
Lockeroo.payment_router
-------------------------
This module provides endpoint routing for payment functionalities

Key Features:
    - Provides payment authorization and verification endpoints
    - Handles payment method selection

Dependencies:
    - fastapi
    - beanie
"""
# Basics
from typing import Annotated, Optional
from bson.objectid import ObjectId
# Database utils
from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import APIRouter, Depends, Path, Query, status
# Entities
from src.entities.user_entity import User
# Models
from lockeroo_models.session_models import SessionView
from lockeroo_models.station_models import PaymentMethod
# Services
from src.services import session_services
from src.services.auth_services import auth_check
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger_service as logger

# Create the router
payment_router = APIRouter()

### REST ENDPOINTS ###


@payment_router.put(
    '/{session_id}/method/select',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description="Select a payment method for a session")
@handle_exceptions(logger)
async def choose_session_payment_method(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    payment_method: Annotated[PaymentMethod, Query(
        description='Payment method to be used.')],
    user: User = Depends(auth_check),
):
    """Handle request to select a payment method"""
    logger.info((f"User '{user.fief_id}' is choosing a "
                f"payment method for session '#{session_id}'."), session_id=session_id)
    return await session_services.handle_payment_selection(
        user=user,
        session_id=ObjId(session_id),
        payment_method=payment_method
    )


@payment_router.patch(
    '/{session_id}/verification/initiate',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Request to enter the verification queue of a session')
@handle_exceptions(logger)
async def request_session_verification(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
):
    """Handle request to enter the verification queue of a session"""
    logger.info(
        (f"User '{user.fief_id}' is requesting to conduct a "
         f"verification."), session_id=session_id)
    return await session_services.handle_verification_request(
        session_id=ObjId(session_id),
        user=user)


@payment_router.put(
    '/{session_id}/verification/complete',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Report a successful verification for a payment')
@handle_exceptions(logger)
async def report_session_verification(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
):
    """Handle request to report a successful verification"""
    logger.info(
        (f"User '{user.fief_id}' is reporting a successful "
         f"verification."), session_id=session_id)
    return await session_services.handle_verification_completion(
        session_id=ObjId(session_id),
        user=user
    )


@payment_router.patch(
    '/{session_id}/initiate',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Request to enter the payment phase of a session')
@handle_exceptions(logger)
async def request_session_payment(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
):
    """Handle request to enter the payment phase of a session"""
    logger.info(
        (f"User '{user.fief_id}' is requesting to "
         f"conduct a payment"), session_id=session_id)
    return await session_services.handle_payment_request(
        session_id=ObjId(session_id),
        user=user
    )


@payment_router.patch(
    '/{session_id}/complete',
    response_model=Optional[SessionView],
    status_code=status.HTTP_202_ACCEPTED,
    description='Report a successful payment for a session')
@handle_exceptions(logger)
async def report_session_payment(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
):
    """Handle request to report a successful payment"""
    logger.info(
        (f"User '{user.fief_id}' is reporting a successful "
         f"payment for session"), session_id=session_id)
    return await session_services.handle_payment_completion(
        session_id=ObjId(session_id),
        user=user
    )
