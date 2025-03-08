"""Provides utility functions for the auth backend."""
# Basics
from typing import List
from uuid import UUID
import configparser
# FastAPI
from fastapi import Depends, Request, HTTPException
from fastapi.security import OAuth2AuthorizationCodeBearer
# Fief
from fief_client import FiefAsync, FiefAccessTokenInfo
from fief_client.integrations.fastapi import FiefAuth
# Entities
from src.entities.user_entity import User
# Models
from src.models.user_models import UserModel, AuthenticatedUserModel
from src.models.permission_models import PERMISSION
# Exception

base_config = configparser.ConfigParser()
base_config.read('.env')


def init_fief():
    """Initialize the Fief client."""
    fiefinst = FiefAsync(
        base_config.get('FIEF', 'BASE_URL'),
        base_config.get('FIEF', 'CLIENT_ID'),
        base_config.get('FIEF', 'CLIENT_SECRET')
        # redirect_uris=[f"{os.getenv('API_BASE_URL')}/docs/oauth2-redirect",
        #               f"{os.getenv('API_BASE_URL')}/auth/callback"]
    )

    scheme = OAuth2AuthorizationCodeBearer(
        base_config.get('FIEF', 'BASE_URL') + "/authorize",
        base_config.get('FIEF', 'BASE_URL') + "/api/token",
        # redirect_url=f"{os.getenv('API_BASE_URL')}/docs/oauth2-redirect",
        scopes={"openid": "openid", "offline_access": "offline_access"},
        auto_error=False,
    )

    return FiefAuth(fiefinst, scheme)


fief = init_fief()


async def auth_check(
        request: Request,
        token_info: FiefAccessTokenInfo = Depends(fief.authenticated())) -> User:
    """Middlepoint that verifies the user identity and permissions."""
    provided_id: UUID = None
    # 1. Check if this is a load case scenario
    load_test_key = request.headers.get("X-Locust")
    if load_test_key == base_config.read("LOCUST", "LOAD_KEY"):
        test_user_id = request.headers.get("X-Locust-ID")
        if test_user_id:
            print("Load test scenario, bypassing.")
            provided_id = request.headers.get("X-Locust-ID")
            token_info['permissions'] = [
                e.value for e in PERMISSION if e != PERMISSION.FIEF_ADMIN]
    elif token_info is not None:
        provided_id = token_info['id']

    # Get the user's database entry
    if provided_id is None:
        raise HTTPException(status_code=401)
    usr = await UserModel.find_one(
        UserModel.fief_id == provided_id)
    if not usr:
        usr = await UserModel.insert(
            UserModel(fief_id=provided_id))

    usr = usr.model_dump()
    usr.update(
        {'permissions': token_info['permissions']})

    return User(AuthenticatedUserModel(**usr))


def permission_check(
        required_permissions: List[PERMISSION],
        obtained_permissions: List[PERMISSION]
):
    """Checks if a user has the required permissions."""
    missing_permissions = [
        i for i in required_permissions if i not in obtained_permissions]

    # if missing_permissions:
    #    raise InvalidPermissionException(missing_permissions)
