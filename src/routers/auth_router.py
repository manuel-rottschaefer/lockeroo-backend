"""
This file contains the router for the authentification related endpoints
"""
# Basics
import os

# FastAPI
from fastapi import APIRouter

# Fief
from src.services.auth_services import fief

# Create the router
auth_router = APIRouter()


@auth_router.get("/callback")
async def auth_callback(code: str):
    """Handle the OAuth2 callback"""
    token = await fief.auth_callback(
        code,
        redirect_uri=f"{os.getenv('API_BASE_URL')}/auth/callback"
    )
    return token
