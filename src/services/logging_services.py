"""Provides utility functions for the logging manager."""

# Basics
import logging
# Types
from datetime import datetime
from typing import Union

from beanie import PydanticObjectId as ObjId

# Service exceptions
from src.services.exception_services import ServiceExceptions

# UNIX_TS = (datetime.now() - datetime(1970, 1, 1)).total_seconds()
LOGFILE = f"src/logs/{datetime.today().strftime('%Y-%m-%d')}.log"

# Configure logging
logging.basicConfig(
    filename=LOGFILE,
    encoding="utf-8",
    filemode="a",
    format="{asctime} - {levelname} - {message}",
    style="{",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)


class LoggingService:
    """A central logging service that handles custom error and
     debug messages as well as defined service exceptions."""

    def __init__(self):
        self.logging = logging.getLogger(__name__)

    def debug(self, message: str):
        """Pass message to default logger with level DEBUG"""
        self.logging.debug(message)

    def warning(self, message: str):
        """Pass message to default logger with level DEBUG"""
        self.logging.warning(message)

    def error(self, message: str):
        """Pass message to default logger with level ERROR"""
        self.logging.error(message)

    def info(self, exception: ServiceExceptions,  # pylint: disable=too-many-arguments,too-many-positional-arguments
             session: Union[str, ObjId] = '',
             station: Union[str, ObjId] = '',
             locker: Union[str, ObjId] = '',
             user: Union[str, ObjId] = '',
             detail: str = ''):
        """As the info level is for strictly defined service exceptions,
        it does not accept regular strings as messages.
        The method also only accepts basic information about an incident
        as all details can be looked up in the FastApi log"""
        self.logging.info(exception)


loggers = [name for name, logger in logging.Logger.manager.loggerDict.items()
           if isinstance(logger, logging.Logger)]
for logger in loggers:
    # logging.debug(f'Setting logger {logger} to level state warning.')
    logging.getLogger(logger).setLevel(logging.WARNING)
# logging.getLogger('dotenv').setLevel(logging.WARNING)


# Seperate entries
with open(LOGFILE, 'r', encoding='utf-8') as log:
    lines = log.readlines()
    if not lines or '---' not in lines[-1].strip():
        logging.info(
            '---------------------------------------------------------------')

logger = LoggingService()
