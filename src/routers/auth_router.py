"""
Lockeroo.auth_router
-------------------------
This module provides routing endpoints for authentication using OAuth2 with Fief.

Key Features:
    - Provides callback endpoint for handling OAuth2 authentication.

Dependencies:
    - fastapi
"""
# FastAPI
from fastapi import APIRouter, Request
# Services
from src.services.config_services import cfg


# Create the router
auth_router = APIRouter()


@auth_router.get(
    "/callback", description="Handle the OAuth2 callback",)
async def auth_callback(code: str, request: Request):
    """Handle the OAuth2 callback"""
    token = await request.app.state.fief.auth_callback(
        code,
        redirect_uri=f"{cfg.get('ENDPOINTS', 'API_BASE_URL')}/auth/callback"
    )
    return token
