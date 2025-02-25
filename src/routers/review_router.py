"""
    This module contains the FastAPI router for handling reviews.
"""
# Types
from typing import Annotated
from bson.objectid import ObjectId
from uuid import uuid4
from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import APIRouter, Depends, Header, Path, Query, status
# Models
from src.models.review_models import ReviewView
from src.models.user_models import UserModel
from src.services import review_services
from src.services.auth_services import require_auth
# Services
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger_service as logger
# Create the router
review_router = APIRouter()


@review_router.get(
    '/{session_id}',
    response_model=ReviewView,
    status_code=status.HTTP_200_OK,
    description='Get the review of a session.')
@handle_exceptions(logger)
async def get_review(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    _user: Annotated[str, Header(
        alias="user", example=uuid4(),
        description="The user who is requesting details about the review.")],
    access_info: UserModel = Depends(require_auth),
):
    """Handle request to get a review for a session"""
    return await review_services.get_session_review(
        session_id=ObjId(session_id),
        user=access_info
    )


@review_router.put(
    '/{session_id}/submit',
    response_model=ReviewView,
    status_code=status.HTTP_201_CREATED,
    description='Submit a review for a completed session.')
@handle_exceptions(logger)
async def submit_review(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    experience_rating: Annotated[
        int, Query(ge=1, le=5, escription="Star rating of the experience")],
    cleanliness_rating: Annotated[
        int, Query(ge=1, le=5, description="Star rating of the hygiene.")],
    details: Annotated[str, Query(
        max_length=500, description="Comment by the user.")],
    _user: Annotated[str, Header(
        alias="user", example=uuid4(),
        description="User UUID (only for debug)")],
    access_info: UserModel = Depends(require_auth),
):
    """Handle request to submit a review for a completed session"""
    return await review_services.handle_review_submission(
        session_id=session_id,
        user=access_info,
        experience_rating=experience_rating,
        cleanliness_rating=cleanliness_rating,
        details=details
    )
