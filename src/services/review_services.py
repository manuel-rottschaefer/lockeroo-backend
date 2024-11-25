"""Provides utility functions for the review management backend."""

# Basics
from datetime import datetime

# Types
from uuid import UUID
from typing import Optional
from beanie import PydanticObjectId as ObjId

# FastAPI
from fastapi import HTTPException

# Entities
from src.entities.session_entity import Session

# Nodels
from src.models.review_models import ReviewModel
from src.models.session_models import SessionModel, SessionStates

# Services
from src.services.exceptions import ServiceExceptions
from src.services.logging_services import logger


async def handle_review_submission(session_id: ObjId,
                                   user_id: UUID,
                                   experience_rating: int,
                                   cleanliness_rating: int,
                                   details: str):
    """Submit a review for a session."""
    # 1: Get session
    session: SessionModel = await SessionModel.find_one(
        SessionModel.id == session_id,
        SessionModel.assigned_user == user_id
    )
    if not session:
        raise HTTPException(status_code=404,
                            detail=ServiceExceptions.SESSION_NOT_FOUND.value)

    # 2: Check if the session has already been completed
    if session.session_state != SessionStates.COMPLETED:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    user=user_id, session=session_id)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.WRONG_SESSION_STATE.value)

    # 3: Then insert the review into the database
    await ReviewModel(
        assigned_session=session.id,
        submitted_ts=datetime.now(),
        experience_rating=experience_rating,
        cleanliness_rating=cleanliness_rating,
        details=details
    ).insert()


async def get_session_review(session_id: ObjId, user_id: UUID) -> Optional[ReviewModel]:
    """Return a review for a session from the database."""
    # 1: Find the review entry
    review: ReviewModel = await ReviewModel.find_one(
        ReviewModel.assigned_session == session_id
    )
    if not review:
        logger.info(ServiceExceptions.REVIEW_NOT_FOUND, session=session_id)
        return None

    # 2: Find the assigned session
    session: Session = await Session().fetch(session_id=review.assigned_session.id)
    if not session:
        logger.warning(
            f'Session {review.assigned_session.id} does not exist, but should.')
        return None
    if session.assigned_user != user_id:
        raise HTTPException(
            status_code=401, detail=ServiceExceptions.NOT_AUTHORIZED.value)

    return review
