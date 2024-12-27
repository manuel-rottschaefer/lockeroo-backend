"""Provides custom service exceptions for the backend."""
##########
# In HTTP services, we raise custom exceptions if something actually unexpected happens
# and http exceptions if the user requested weird shit.
#########

import traceback
# Basics
from functools import wraps

# Exceptions
from fastapi import HTTPException

from src.exceptions.station_exceptions import InvalidTerminalStateException


def handle_exceptions(logging_service):
    """Handle FastAPI Endpoint Exceptions."""
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
            except Exception as e:
                logging_service.error(f"Unhandled exception: {
                                      traceback.format_exc()}")
                raise HTTPException(
                    status_code=500, detail="Internal Server Error") from e
        return wrapper
    return decorator
