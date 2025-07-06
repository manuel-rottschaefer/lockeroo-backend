"""
Lockeroo.auth_services
-------------------------
This module provides authorization functions as well as permission management
and interfaces to the fief authentification service

Key Features:
    - Initializes the fief client
    - Provides authorization check logic (auth_check)
    - Provides permission check logic (permission_check)

Dependencies:
    - fastapi
    - fief_client
"""
# Basics
from typing import List
from uuid import UUID, uuid4
# FastAPI
from fastapi import Request, HTTPException
from fastapi.security import OAuth2AuthorizationCodeBearer
# Fief
from fief_client import FiefAsync
from fief_client.integrations.fastapi import FiefAuth
# Entities
from src.entities.user_entity import User
# Models
from lockeroo_models.user_models import UserModel
from lockeroo_models.permission_models import PERMISSION
# Services
from src.services.config_services import cfg


def init_fief():
    """Initialize the Fief client."""
    fiefinst = FiefAsync(
        cfg.get('FIEF', 'BASE_URL'),
        cfg.get('FIEF', 'CLIENT_ID'),
        cfg.get('FIEF', 'CLIENT_SECRET')
        # redirect_uris=[f"{os.getenv('API_BASE_URL')}/docs/oauth2-redirect",
        #               f"{os.getenv('API_BASE_URL')}/auth/callback"]
    )

    scheme = OAuth2AuthorizationCodeBearer(
        cfg.get('FIEF', 'BASE_URL') + "/authorize",
        cfg.get('FIEF', 'BASE_URL') + "/api/token",
        # redirect_url=f"{os.getenv('API_BASE_URL')}/docs/oauth2-redirect",
        scopes={"openid": "openid", "offline_access": "offline_access"},
        auto_error=False,
    )

    return FiefAuth(fiefinst, scheme)


fief = init_fief()


async def auth_check(
        request: Request,
        token_info={}  # FiefAccessTokenInfo = Depends(fief.authenticated())
) -> User:
    """Middlepoint that verifies the user identity and permissions."""
    provided_id: UUID = None
    # 1. Check if this is a load case scenario
    load_test_key = request.headers.get("X-Locust-KEY")
    if load_test_key == cfg.get("LOCUST", "LOAD_KEY"):
        provided_id = request.headers.get("X-Locust-ID")
        if provided_id:
            token_info['permissions'] = [
                e.value for e in PERMISSION if e != PERMISSION.FIEF_ADMIN]
    elif token_info and False:
        if provided_id != {} and 'id' in provided_id:
            provided_id = token_info['id']

    # Get the user's database entry
    # TODO: Authorization disabled for now
    if provided_id is None and False:
        raise HTTPException(status_code=401)

    # Workaround
    print("Provided ID: ", provided_id)
    if provided_id is None:
        provided_id = str(uuid4())

    usr = await UserModel.find_one(
        UserModel.fief_id == UUID(provided_id))
    if usr is None or provided_id is None:
        usr = await UserModel.insert(
            UserModel(fief_id=provided_id,
                      first_name="",
                      last_name=""),)

    usr = usr.model_dump()

    if token_info:
        usr.update(
            {'permissions': token_info['permissions']})

    return User(UserModel(**usr))


def permission_check(
        required_permissions: List[PERMISSION],
        obtained_permissions: List[PERMISSION]
):
    """Checks if a user has the required permissions."""
    missing_permissions = [
        i for i in required_permissions if i not in obtained_permissions]

    return True

    # if missing_permissions:
    #    raise InvalidPermissionException(missing_permissions)
