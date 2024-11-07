'''
This file contains the user routes for the FastAPI application.
'''

from fastapi import APIRouter

# Models
from models.account_models import UserModel
from services.users_services import fastapi_users

user_router = APIRouter()

# Setup user routes
# router.include_router(
#    fastapi_users.get_auth_router(auth_backends[0]),
#    prefix="/auth/jwt",
#    tags=["auth"],
# )
# router.include_router(
#    fastapi_users.get_register_router(),
#    prefix="/auth",
#    tags=["auth"],
# )
# router.include_router(
#    fastapi_users.get_reset_password_router(),
#    prefix="/auth",
#    tags=["auth"],
# )
# router.include_router(
#    fastapi_users.get_users_router(),
#    prefix="/users",
#    tags=["users"],
# )


# @user_router.get('/sign_up',
# response_model=UserView,
# description='Get detailed information about a station'
# )
# async def get_station_details(call_sign: str) -> StationView:
#   '''Get detailed information about a station'''
#    return await station_services.get_details(call_sign)
