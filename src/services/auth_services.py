"""
This module provides authentification services.
"""

# Basics
import os

# FastAPI
from fastapi.security import OAuth2AuthorizationCodeBearer

# Fief
from fief_client import FiefAsync
from fief_client.integrations.fastapi import FiefAuth


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
