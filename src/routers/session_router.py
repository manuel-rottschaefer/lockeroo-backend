'''
    This module contains the FastAPI router for handling requests related sessions.
'''
# Basics
from typing import List

# Database utils
from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import APIRouter, HTTPException

from src.models.review_models import ReviewModel
# Models
from src.models.session_models import SessionView
from src.models.action_models import ActionView
# Services
from ..services import review_services, session_services, action_services
from ..services.logging_services import logger

sessionRouter = APIRouter()


### Error handling ###
# @sessionRouter.exception_handler(HTTPException)
# async def http_exception_handler(request, exc):
#    message = str(exc.detail)
#    return JSONResponse({"message": message}, status_code=exc.status_code)


### REST ENDPOINTS ###


@sessionRouter.get('/{session_id}/details',
                   response_model=SessionView,
                   description='Get the details of a session including (active) time, current price and locker state.')
async def get_session_details(session_id: str):
    '''Return the details of a session. This is supposed to be used for refreshing the app-state in case of disconnect or re-open.'''
    return await session_services.get_details(ObjId(session_id))


@sessionRouter.post('/create', response_model=SessionView,
                    description='Request a new session at a given station')
async def request_new_session(user_id: str,
                              station_callsign: str,
                              locker_type: str = ''):
    '''Handle request to create a new session'''
    if not user_id or not station_callsign or not locker_type:
        raise HTTPException(status_code=422)
    try:
        return await session_services.handle_creation_request(
            user_id, station_callsign, locker_type)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500) from e


@sessionRouter.put('/{sessionID}/cancel',
                   response_model=SessionView,
                   description='Request to cancel a locker session before it has been started')
async def request_session_cancel(session_id: str, user_id: str):
    '''Handle request to cancel a locker session'''
    if not session_id:
        raise HTTPException(status_code=422)
    try:
        return await session_services.handle_cancel_request(session_id, user_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500) from e


@sessionRouter.put('/{session_id}/payment/select',
                   response_model=SessionView,
                   description="Select a payment method for a session")
async def choose_session_payment_method(session_id: str, user_id: str, payment_method: str):
    '''Handle request to select a payment method'''
    if not session_id or not payment_method:
        raise HTTPException(status_code=422)
    try:
        return await session_services.handle_payment_selection(ObjId(session_id),
                                                               ObjId(
            user_id),
            payment_method)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500) from e


@ sessionRouter.put('/{session_id}/payment/verify',
                    response_model=SessionView,
                    description='Request to enter the verification queue of a session')
async def request_session_verification(session_id: str, user_id: str):
    '''Handle request to enter the verification queue of a session'''
    if not session_id or not user_id:
        raise HTTPException(status_code=422)
    try:
        return await session_services.handle_verification_request(ObjId(session_id), ObjId(user_id))
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500) from e


@ sessionRouter.put('/{session_id}/hold',
                    response_model=SessionView,
                    description='Request to hold (pause) a locker session')
async def request_session_hold(session_id: str, user_id: str):
    '''Handle request to pause a locker session'''
    if not session_id or not user_id:
        raise HTTPException(status_code=422)
    try:
        return await session_services.handle_hold_request(ObjId(session_id), ObjId(user_id))
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500) from e


@ sessionRouter.put('/{session_id}/payment',
                    response_model=SessionView,
                    description='Request to enter the payment phase of a session')
async def request_session_payment(session_id: str, user_id: str):
    '''Handle request to enter the payment phase of a session'''
    if not session_id or not user_id:
        raise HTTPException(status_code=422)
    try:
        return await session_services.handle_payment_request(ObjId(session_id), ObjId(user_id))
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500) from e


@ sessionRouter.get('/{session_id}/review',
                    response_model=ReviewModel,
                    description='Get the review for a session.')
async def get_review(session_id: str, user_id: str):
    '''Handle request to get a review for a session'''
    try:
        return await review_services.get_session_review(session_id, user_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500) from e


@ sessionRouter.put('/{session_id}/review/submit',
                    response_model=ReviewModel,
                    description='Submit a review for a completed session.')
async def submit_review(session_id: str, user_id: str,
                        experience_rating: int, cleanliness_rating: int, details: str):
    '''Handle request to submit a review for a completed session'''
    try:
        return await review_services.handle_review_submission(session_id, user_id,
                                                              experience_rating,
                                                              cleanliness_rating, details)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500) from e


@sessionRouter.get('/{session_id}/history',
                   response_model=List[ActionView],
                   description="Get a list of all actions of a session.")
async def get_session_history(session_id: str, _user_id: str):
    '''Handle request to obtain a list of all actions from a session'''
    try:
        return await action_services.get_session_history(session_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500) from e
