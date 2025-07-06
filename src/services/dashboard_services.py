"""
Lockeroo.dashboard_services
-------------------------
This module provides dashboard endpoint logic

Key Features:
    - Provides handlers for various dashboard endpoints

Dependencies:
    - beanie
"""
# Basics
from datetime import timedelta
# Beanie
from beanie.operators import In
# Entities
from src.entities.user_entity import User
# Models
from lockeroo_models.session_models import ACTIVE_SESSION_STATES, SessionModel
from lockeroo_models.permission_models import PERMISSION
# Services
from src.services.auth_services import permission_check


async def get_active_session_count(user: User):
    """Get the amount of currently active sessions."""
    # 1: Check permissions
    permission_check([PERMISSION.FIEF_ADMIN], user.doc.permissions)

    # 2: Return active session count
    return await SessionModel.find(
        In(SessionModel.session_state, ACTIVE_SESSION_STATES),
    ).to_list()


async def get_system_locker_utilization(
        user: User,
        timespan: timedelta) -> float:
    """Get the fraction of utilized lockers in relation to available ones.
     If no timespan is given, the current utilization is returned."""
    # TODO: Also implement this for stations and lockers
    # 1: Check permissions
    permission_check([PERMISSION.FIEF_ADMIN], user.doc.permissions)

    # 2: Get amount of session duration in the given timespan
    total_session_duration = 0

    # 3: Calculate utilization
    utilization = total_session_duration / timespan

    return utilization
