"""Provides utility functions for the auth backend."""

# Basics
import os
from functools import wraps

# FastAPI
from fastapi import Header
from fastapi.security import OAuth2AuthorizationCodeBearer
# Fief
from fief_client import FiefAccessTokenInfo, FiefAsync
from fief_client.integrations.fastapi import FiefAuth

# Models
from src.models.user_models import UserModel

# Types
from uuid import UUID
from typing import Annotated


async def require_auth(user: Annotated[str | None, Header()] = None):
    """Add authorization middleware to an endpoint."""
    if user:
        user_model = await UserModel.find(UserModel.fief_id == UUID(user)).first_or_none()
        if not user_model:
            user_model = await UserModel.insert(UserModel(fief_id=user))

    return user_model


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
