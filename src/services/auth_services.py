"""Provides utility functions for the auth backend."""

# Basics
import os
from typing import Annotated
# Types
from uuid import UUID

# FastAPI
from fastapi import Header
from fastapi.security import OAuth2AuthorizationCodeBearer
# Fief
from fief_client import FiefAsync  # , FiefAccessTokenInfo
from fief_client.integrations.fastapi import FiefAuth

# Entities
from src.entities.user_entity import User
# Models
from src.models.user_models import UserModel


async def require_auth(user: Annotated[str | None, Header()] = None):
    """Add authorization middleware to an endpoint."""
    if user:
        user_model = await UserModel.find_one(UserModel.fief_id == UUID(user))
        if not user_model:
            user_model = await UserModel.insert(UserModel(fief_id=user))

    return User(user_model)


fief = FiefAsync(
    os.getenv('FIEF_BASE_URL'),
    os.getenv('FIEF_CLIENT_ID'),
    os.getenv('FIEF_CLIENT_SECRET'),
    # redirect_uris=[f"{os.getenv('API_BASE_URL')}/docs/oauth2-redirect",
    #               f"{os.getenv('API_BASE_URL')}/auth/callback"]
)

scheme = OAuth2AuthorizationCodeBearer(
    os.getenv('FIEF_BASE_URL') + "/authorize",
    os.getenv('FIEF_BASE_URL') + "/api/token",
    # redirect_url=f"{os.getenv('API_BASE_URL')}/docs/oauth2-redirect",
    scopes={"openid": "openid", "offline_access": "offline_access"},
    auto_error=False,
)

auth = FiefAuth(fief, scheme)
