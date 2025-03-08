"""
    This module contains the FastAPI router for handling reviews.
"""
# Types
from typing import Annotated
from bson.objectid import ObjectId
from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import APIRouter, Depends, Path, Query, status
# Models
from src.models.review_models import ReviewView
from src.services import review_services
from src.services.auth_services import auth_check
# Entities
from src.entities.user_entity import User
# Services
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger_service as logger
# Create the router
review_router = APIRouter()


@review_router.get(
    '/{session_id}',
    tags=['review'],
    response_model=ReviewView,
    status_code=status.HTTP_200_OK,
    description='Get the review of a session.')
@handle_exceptions(logger)
async def get_review(
    session_id: Annotated[str, Path(
        pattern='^[a-fA-F0-9]{24}$', example=str(ObjectId()),
        description='Unique identifier of the session.')],
    user: User = Depends(auth_check)
):
    """Handle request to get a review for a session"""
    return await review_services.get_session_review(
        user=user,
        session_id=ObjId(session_id),
    )


@review_router.put(
    '/{session_id}/submit',
    tags=['review'],
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
    user: User = Depends(auth_check)
):
    """Handle request to submit a review for a completed session"""
    return await review_services.handle_review_submission(
        user=user,
        session_id=session_id,
        experience_rating=experience_rating,
        cleanliness_rating=cleanliness_rating,
        details=details
    )
