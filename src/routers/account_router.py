'''
This file contains the router for the account related endpoints
'''

# Types
from typing import List
from beanie import PydanticObjectId as ObjId
# FastAPI
from fastapi import APIRouter, HTTPException
# Models
from src.models.session_models import CompletedSession
from src.models.account_models import AccountSummary

# Initialize the router
accountRouter = APIRouter()


@accountRouter.get('/history',
                   response_model=List[CompletedSession],
                   description='Get session details')
async def get_account_history(user_id: str, count: int):
    '''Get a list of completed sessions of this account'''

    # Get station data from the database
    session_data = await CompletedSession.find(
        CompletedSession.userID == ObjId(user_id)
    ).limit(count).sort(CompletedSession.completedTS).to_list(count)

    if not session_data:
        raise HTTPException(status_code=404, detail="No sessions found")

    return session_data


@accountRouter.get('/summary',
                   response_model=AccountSummary,
                   description='Get a quick summary of the user activity')
async def get_account_summary(_user_id: str):
    '''Return user summary'''
    return None
