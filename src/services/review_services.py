"""Provides utility functions for the review management backend."""

# Basics
from datetime import datetime
from typing import Optional

# Beanie
from beanie import PydanticObjectId as ObjId

from src.exceptions.review_exceptions import ReviewNotFoundException
# Exceptions
from src.exceptions.session_exceptions import (InvalidSessionStateException,
                                               SessionNotFoundException)
from src.exceptions.user_exceptions import UserNotAuthorizedException
# Nodels
from src.models.review_models import ReviewModel
from src.models.session_models import SessionModel, SessionState
from src.models.user_models import UserModel


async def handle_review_submission(session_id: ObjId,
                                   user: UserModel,
                                   experience_rating: int,
                                   cleanliness_rating: int,
                                   details: str):
    """Submit a review for a session."""
    # 1: Get session
    session: SessionModel = await SessionModel.find_one(
        SessionModel.id == session_id,
        SessionModel.assigned_user == user
    )
    if not session.exists:
        raise SessionNotFoundException(user_id=user.fief_id)

    # 2: Check if the session has already been completed
    if session.session_state != SessionState.COMPLETED:
        raise InvalidSessionStateException(
            session_id=session_id,
            expected_states=[SessionState.COMPLETED],
            actual_state=session.session_state)

    # 3: Then insert the review into the database
    return await ReviewModel(
        assigned_session=session.id,
        submitted_at=datetime.now(),
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
        ReviewModel.assigned_session.id == session_id  # pylint: disable=no-member
    )
    if not review:
        raise ReviewNotFoundException(review_id=session_id)

    # 2: Check if the user is authorized to view the review
    await review.doc.fetch_link(ReviewModel.assigned_session)
    if review.assigned_session.doc.assigned_user != user:
        raise UserNotAuthorizedException(user_id=user.id)

    return review
