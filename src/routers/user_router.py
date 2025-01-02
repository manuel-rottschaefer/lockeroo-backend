# Basics
from typing import Annotated, Optional

from beanie import PydanticObjectId as ObjId
# FastAPI & Beanie
from fastapi import APIRouter, Path, status

# Exceptions
from src.models.session_models import SessionView
# Models
from src.models.user_models import (
    UserSummary, UserQuickStats)
# Services
from src.services import user_services
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger

# Create the router
user_router = APIRouter()


@ user_router.get(
    '/{user_id}/',
    response_model=Optional[UserSummary],
    status_code=status.HTTP_200_OK,
    description='Get the details of a user.'
)
@ handle_exceptions(logger)
async def get_user_details(
    user_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
) -> UserSummary:
    """Get the details of a user."""
    return await user_services.get_details(
        user_id=ObjId(user_id)
    )


@ user_router.get(
    '/{user_id}/quick_stats',
    response_model=UserQuickStats,
    status_code=status.HTTP_200_OK,
    description='Get the quick stats of a user.')
@ handle_exceptions(logger)
async def get_user_quick_stats(
    user_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
) -> UserQuickStats:
    """Get the quick stats of a user."""
    return await user_services.get_quick_stats(
        user_id=ObjId(user_id)
    )


@ user_router.get(
    '/{user_id}/active_session',
    response_model=Optional[SessionView],
    status_code=status.HTTP_200_OK,
    description='Get the active session of a user, if any.'
)
@ handle_exceptions(logger)
async def get_active_session(
    user_id: Annotated[str, Path(pattern='^[a-fA-F0-9]{24}$')],
) -> SessionView:
    """Get the active session of a user, if any."""
    return await user_services.get_active_session(
        user_id=ObjId(user_id)
    )
