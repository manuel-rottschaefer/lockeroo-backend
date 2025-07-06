"""
Lockeroo.dashboard router
-------------------------
This module provides endpoint routing for dashboard functionalities

Key Features:
    - Provides various dashboard endpoints

Dependencies:
    - fastapi
"""
# Basics
from datetime import timedelta
# FastAPI
from fastapi import APIRouter, Depends
# Entities
from src.entities.user_entity import User
# Services
from src.services.dashboard_services import (
    get_active_session_count,
    get_system_locker_utilization
)
from src.services.exception_services import handle_exceptions
from src.services.auth_services import auth_check
from src.services.logging_services import logger_service as logger

# Create the router
dashboard_router = APIRouter()

### Session dashboard ###


@dashboard_router.get(
    '/active_session_count/', description='Get the amount of currently active sessions.')
@handle_exceptions(logger)
async def active_session_count(
    user: User = Depends(auth_check)
) -> int:
    """Get the amount of all active sessions in the system."""
    return get_active_session_count(user)


@dashboard_router.get(
    '/locker_utilization_rate',
    description=("Get the fraction of utilized lockers in relation to available ones."
                 "If no timespan is given, the current utilization is returned.")
)
@handle_exceptions(logger)
async def locker_utilization_rate(
    user: User = Depends(auth_check),
    timespan: timedelta = timedelta(seconds=0)
) -> float:
    ("Get the fraction of utilized lockers in relation to available ones."
     "If no timespan is given, the current utilization is returned.")
    return get_system_locker_utilization(
        user, timespan
    )
