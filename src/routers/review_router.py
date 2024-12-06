"""
    This module contains the FastAPI router for handling reviews.
"""
# Basics
from typing import Annotated

# Database utils
from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import APIRouter, Path, Query, Depends, Header

# Models
from src.models.review_models import ReviewModel
from src.models.user_models import UserModel

# Services
from src.services.exceptions import handle_exceptions
from src.services.logging_services import logger
from src.services.auth_services import require_auth
from src.services import review_services

# Create the router
review_router = APIRouter()


@ review_router.get('/{session_id}',
                    response_model=ReviewModel,
                    description='Get the review of a session.')
@ handle_exceptions(logger)
async def get_review(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    user: str = Header(default=None),
    access_info: UserModel = Depends(require_auth),
):
    """Handle request to get a review for a session"""
    return await review_services.get_session_review(
        session_id=ObjId(session_id),
        user=access_info
    )


@ review_router.put('/{session_id}/submit',
                    response_model=ReviewModel,
                    description='Submit a review for a completed session.')
@ handle_exceptions(logger)
async def submit_review(
    session_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
    experience_rating: Annotated[int, Query(ge=1, le=5)],
    cleanliness_rating: Annotated[int, Query(ge=1, le=5)],
    details: str,
    user: str = Header(default=None),
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
