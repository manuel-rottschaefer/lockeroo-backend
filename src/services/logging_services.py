"""Provides utility functions for the logging manager."""

# Basics
from typing import Union
import logging

# Types
from datetime import datetime
from beanie import PydanticObjectId as ObjId

# Service exceptions
from src.services.exceptions import ServiceExceptions

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
        ### Stations ###
        if exception == ServiceExceptions.STATION_NOT_FOUND:
            self.logging.info("Could not find station '%s'.", station)

        elif exception == ServiceExceptions.STATION_NOT_AVAILABLE:
            self.logging.info(
                "Station '%s' is currently not available.", station)

        elif exception == ServiceExceptions.STATION_PAYMENT_NOT_AVAILABLE:
            self.logging.info(
                "Payment method '%s' is currently not supported.", detail)

        elif exception == ServiceExceptions.INVALID_PAYMENT_METHOD:
            self.logging.info(
                "Session '%s' does not support payment method '%s'.", session, detail)

        elif exception == ServiceExceptions.PAYMENT_METHOD_NOT_SUPPORTED:
            self.logging.info(
                "Station '%s' does currently not support %s as a payment method", station, detail)

        ### Sessions ###
        elif exception == ServiceExceptions.SESSION_NOT_FOUND:
            if session:
                self.logging.info(
                    "Could not find session '%s' in database.", session)
            elif station:
                self.logging.info(
                    "Could not find an active session at station '%s'.", station)

        elif exception == ServiceExceptions.WRONG_SESSION_STATE:
            self.logging.info(
                "Session '%s' is in state '%s' and can therefore not be handled.",
                session, detail.name)

        elif exception == ServiceExceptions.SESSION_EXPIRED:
            self.logging.info(
                "Session '%s' expired while waiting for %s", session, detail)

        elif exception == ServiceExceptions.PAYMENT_METHOD_NOT_SUPPORTED:
            self.logging.info(
                "Payment method '%s' does not exist or is not available for session '%s'.",
                detail, session)

        ### Lockers ###
        elif exception == ServiceExceptions.LOCKER_NOT_FOUND:
            self.logging.info(
                "Could not find locker #%s at station '%s'.", detail, station)

        elif exception == ServiceExceptions.LOCKER_NOT_AVAILABLE:
            self.logging.info(
                "No locker currently available at station '%s'.", station)

        elif exception == ServiceExceptions.INVALID_LOCKER_STATE:
            self.logging.info(
                "Invalid state reported for locker '%s' at station '%s'.", locker, station)

        ### Users ###
        elif exception == ServiceExceptions.USER_HAS_ACTIVE_SESSION:
            self.logging.info(
                "User '%s' tried to create a session, but already has an active one.", user)

        ### Reviews ###
        elif exception == ServiceExceptions.REVIEW_NOT_FOUND:
            self.logging.info(
                "Could not find review for session '%s'.", session)


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
