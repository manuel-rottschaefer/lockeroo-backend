"""
    This module contains the FastAPI router for handling reviews.
"""
# Basics
from typing import Annotated

# Database utils
from beanie import PydanticObjectId as ObjId

# FastAPI
from fastapi import APIRouter, Path, Query, Depends

# Auth
from fief_client import FiefAccessTokenInfo

# Models
from src.models.review_models import ReviewModel

# Services
from src.services.exceptions import handle_exceptions
from src.services.logging_services import logger
from src.services.auth_services import auth
from src.services import review_services

# Create the router
maintenance_router = APIRouter()
