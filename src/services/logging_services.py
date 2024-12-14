"""Provides utility functions for the logging manager."""

# Basics
import logging
# Types
from datetime import datetime

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

    def info(self, message: str):
        """Pass message to default logger with level INFO"""
        self.logging.info(message)

    def warning(self, message: str):
        """Pass message to default logger with level DEBUG"""
        self.logging.warning(message)

    def error(self, message: str):
        """Pass message to default logger with level ERROR"""
        self.logging.error(message)


def new_log_section():
    """Create a new log section"""
    with open(LOGFILE, 'r', encoding='utf-8') as log:
        lines = log.readlines()
        if not lines or '---' not in lines[-1].strip():
            logging.info(
                '--------------------------------------------------------------')


def init_loggers():
    """Set all loggers to warning level"""

    loggers = [name for name, logger in logging.Logger.manager.loggerDict.items()
               if isinstance(logger, logging.Logger)]
    loggers.append('pymongo')
    for mod_logger in loggers:
        # logging.debug(f'Setting logger {mod_logger} to level state warning.')
        logging.getLogger(mod_logger).setLevel(logging.WARNING)
    new_log_section()
    return LoggingService()


logger = init_loggers()
