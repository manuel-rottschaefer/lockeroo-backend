from src.exceptions.session_exceptions import InvalidSessionStateException
from mocking.dep.mocking_logger import LocustLogger

logger = LocustLogger().logger


def handle_invalid_state(func):
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except InvalidSessionStateException as e:
            logger.error(f"Invalid session state: {str(e)}")
            return None
    return wrapper
