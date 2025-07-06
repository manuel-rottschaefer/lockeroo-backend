"""
Lockeroo.auth_services
-------------------------
This module provides exception handling services

Key Features:
    - Adds exception handling to the FastAPI app

Dependencies:
    - fastapi
"""

# Basics
from functools import wraps
from traceback import format_exc
# FastAPI
from fastapi import HTTPException
# Exceptions
from src.exceptions.station_exceptions import InvalidTerminalStateException
from src.exceptions.locker_exceptions import LockerNotAvailableException


def handle_exceptions(logging_service):
    """Handle FastAPI Endpoint Exceptions."""
    # TODO: Check if this overlaps with other handlers
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException as e:
                logging_service.error(f"HTTPException: {e.detail}")
                raise e
            except InvalidTerminalStateException as e:
                logging_service.error(str(e))
            except LockerNotAvailableException as e:
                logging_service.debug(str(e))
            except Exception as e:
                logging_service.error(
                    (f"Unhandled exception: {format_exc()}"))
                raise HTTPException(
                    status_code=500, detail="Internal Server Error") from e
        return wrapper
    return decorator
