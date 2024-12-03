"""Provides utility functions for the auth backend."""

# Basics
from functools import wraps
import os

# FastAPI
from fastapi.security import OAuth2AuthorizationCodeBearer

# Fief
from fief_client import FiefAsync, FiefAccessTokenInfo
from fief_client.integrations.fastapi import FiefAuth


def require_auth(func):
    """Add authorization middleware to an endpoint."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Check if authentication is enabled
        auth_enabled = os.getenv('AUTH_ENABLED').lower() == 'TRUE'

        if auth_enabled:
            access_info: FiefAccessTokenInfo = kwargs.get('access_info', None)
            if not access_info:
                access_info = await auth.authenticated()
                kwargs['access_info'] = access_info
        else:
            # Use the provided account ID if available, otherwise use the default account ID
            account_id = kwargs.get(
                'account_id') or os.getenv('DEFAULT_USER_ID')
            kwargs['access_info'] = {'id': account_id}

        return await func(*args, **kwargs)

    return wrapper


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
