"""Provides custom service exceptions for the backend."""
##########
# In HTTP services, we raise custom exceptions if something actually unexpected happens
# and http exceptions if the user requested weird shit.
#########

from enum import Enum
# Basics
from functools import wraps

# Exceptions
from fastapi import HTTPException


def handle_exceptions(logger):
    """Handle FastAPI Endpoint Exceptions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException as e:
                logger.error(f"HTTPException: {e.detail}")
                raise e
            except Exception as e:
                logger.error(f"Unhandled exception: {str(e)}")
                raise HTTPException(
                    status_code=500, detail="Internal Server Error") from e
        return wrapper
    return decorator


class ServiceExceptions(Enum):
    """Custom exceptions for the session services"""

    # Generics
    NOT_AUTHORIZED = 'not_authorized'  # replace
    LIMIT_EXCEEDED = 'limit_exceeded'

    # Stations
    STATION_NOT_FOUND = "station_not_found"
    STATION_NOT_AVAILABLE = "station_not_available"
    STATION_PAYMENT_NOT_AVAILABLE = "station_payment_not_available"
    PAYMENT_METHOD_NOT_SUPPORTED = "payment_method_not_supported"
    INVALID_TERMINAL_STATE = "invalid_terminal_state"  # replace

    # Sessions
    SESSION_NOT_FOUND = "session_not_found"
    WRONG_SESSION_STATE = "invalid_session_state"  # replace
    SESSION_EXPIRED = "session_expired"  # remove
    INVALID_PAYMENT_METHOD = "invalid_payment_method"

    # Locker
    LOCKER_NOT_FOUND = "locker_not_found"
    LOCKER_NOT_AVAILABLE = "locker_not_available"
    INVALID_LOCKER_STATE = "invalid_locker_state"  # replace
    INVALID_LOCKER_TYPE = "invalid_locker_type"

    # Users
    USER_NOT_FOUND = "user_not_found"
    USER_HAS_ACTIVE_SESSION = "user_has_active_session"

    # Reviews
    REVIEW_NOT_FOUND = "review_not_found"
