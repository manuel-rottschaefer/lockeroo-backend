"""
This file contains the router for the authentification related endpoints
"""
# Basics
import os
# FastAPI
from fastapi import APIRouter, Request


# Create the router
auth_router = APIRouter()


@auth_router.get(
    "/callback", description="Handle the OAuth2 callback",)
async def auth_callback(code: str, request: Request):
    """Handle the OAuth2 callback"""
    token = await request.app.state.fief.auth_callback(
        code,
        redirect_uri=f"{os.getenv('API_BASE_URL')}/auth/callback"
    )
    return token
