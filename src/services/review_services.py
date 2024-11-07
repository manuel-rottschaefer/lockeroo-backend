'''
This file contains the services for the review endpoints.
'''

# Basics
from datetime import datetime

# Types
from typing import Optional
from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import HTTPException
# Nodels
from src.models.review_models import ReviewModel
from src.models.session_models import SessionModel, SessionStates
# Services
from ..services.exceptions import ServiceExceptions
from ..services.logging_services import logger


async def handle_review_submission(session_id: ObjId, user_id: ObjId,
                                   experience_rating: int, cleanliness_rating: int, details: str):
    '''Submit a review for a session'''
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


async def get_session_review(session_id: ObjId, _user_id: ObjId) -> Optional[ReviewModel]:
    '''Return a review for a session from the database'''
    review: ReviewModel = await ReviewModel.find_one(
        ReviewModel.assigned_session == session_id
    )
    if not review:
        logger.info(ServiceExceptions.REVIEW_NOT_FOUND, session=session_id)
        return None

    return review
