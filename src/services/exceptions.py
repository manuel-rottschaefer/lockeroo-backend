'''
This module contains custom exceptions for the services.
'''

from enum import Enum


class ServiceExceptions(Enum):
    '''Custom exceptions for the session services'''

    # Stations
    STATION_NOT_FOUND = "station_not_found"
    STATION_NOT_AVAILABLE = "station_not_available"
    STATION_PAYMENT_NOT_AVAILABLE = "station_payment_not_available"
    INVALID_TERMINAL_STATE = "invalid_terminal_state"

    # Sessions
    SESSION_NOT_FOUND = "session_not_found"
    WRONG_SESSION_STATE = "invalid_session_state"
    SESSION_EXPIRED = "session_expired"
    PAYMENT_METHOD_NOT_AVAILABLE = "payment_method_not_available"

    # Locker
    LOCKER_NOT_FOUND = "locker_not_found"
    LOCKER_NOT_AVAILABLE = "locker_not_available"
    INVALID_LOCKER_STATE = "invalid_locker_state"
    INVALID_LOCKER_TYPE = "invalid_locker_type"

    # Users
    USER_NOT_FOUND = "user_not_found"
    USER_HAS_ACTIVE_SESSION = "user_has_active_session"

    # Reviews
    REVIEW_NOT_FOUND = "review_not_found"
