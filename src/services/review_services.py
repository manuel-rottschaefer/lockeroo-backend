"""Provides utility functions for the review management backend."""

# Basics
from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import HTTPException

# Entities
from src.entities.session_entity import Session
# Nodels
from src.models.review_models import ReviewModel
from src.models.session_models import SessionModel, SessionStates
from src.models.user_models import UserModel

# Services
from src.services.logging_services import logger

# Exceptions
from src.exceptions.session_exceptions import (
    SessionNotFoundException,
    InvalidSessionStateException)
from src.exceptions.review_exceptions import ReviewNotFoundException
from src.exceptions.user_exceptions import UserNotAuthorizedException


async def handle_review_submission(session_id: ObjId,
                                   user: UserModel,
                                   experience_rating: int,
                                   cleanliness_rating: int,
                                   details: str):
    """Submit a review for a session."""
    # 1: Get session
    session: SessionModel = await SessionModel.find_one(
        SessionModel.id == session_id,
        SessionModel.user == user
    )
    if not session.exists:
        raise SessionNotFoundException(session_id=session_id)

    # 2: Check if the session has already been completed
    if session.session_state != SessionStates.COMPLETED:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionStates.COMPLETED],
            actual_state=session.session_state)

    # 3: Then insert the review into the database
    await ReviewModel(
        assigned_session=session.id,
        submitted_ts=datetime.now(),
        experience_rating=experience_rating,
        cleanliness_rating=cleanliness_rating,
        details=details
    ).insert()


async def get_session_review(
        session_id: ObjId,
        user: UserModel) -> Optional[ReviewModel]:
    """Return a review for a session from the database."""
    # 1: Find the review entry
    review: ReviewModel = await ReviewModel.find_one(
        ReviewModel.assigned_session == session_id
    )
    if not review:
        raise ReviewNotFoundException(review_id=session_id)

    # 2: Find the assigned session
    session: Session = await Session().find(session_id=review.assigned_session.id)
    if not session.exists:
        logger.warning(
            f'Session {review.assigned_session.id} does not exist, but should.')
        return None
    await session.fetch_link(SessionModel.user)
    if session.user.id != user.id:
        raise UserNotAuthorizedException(user_id=user.id)

    return review
