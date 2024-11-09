"""
This module contains the services for the user model.
"""

# from fastapi_users import FastAPIUsers
# from fastapi_users.authentication import

from beanie import PydanticObjectId as ObjId
from beanie.operators import NotIn
from fastapi_users_db_beanie import BeanieUserDatabase

# Models
from src.models.session_models import SessionModel, SessionStates
from src.models.account_models import AccountModel

# Services
from src.services.logging_services import logger

SECRET = "SECRET"

user_db = BeanieUserDatabase(AccountModel)

# auth_backends = [
#    JWTAuthentication(secret=SECRET, lifetime_seconds=3600,
#                      tokenUrl="auth/jwt/login")
# ]

# fastapi_users = FastAPIUsers(
#    user_db,
# auth_backends,
#    UserModel,
#    UserCreate,
#    UserUpdate,
#    UserDB,
# )


async def has_active_session(user_id: ObjId) -> bool:
    """Check if the given user has an active session"""
    accepted_session_states = [
        SessionStates.COMPLETED, SessionStates.CANCELLED]

    active_session = await SessionModel.find(
        SessionModel.assigned_user == ObjId(user_id),
        NotIn(SessionModel.session_state, accepted_session_states),
    ).first_or_none()

    if active_session:
        logger.info(f"User {user_id} already has an active session.")

    return active_session is not None
