"""Logger for locust"""
from datetime import datetime
import logging


class LocustLogger():
    """Logger for locust"""

    def __init__(self):
        # Create a file handler
        locust_logfile = f"locustt/logs/{
            datetime.today().strftime('%Y-%m-%d')}.log"

        # Create a formatter and add it to the handler
        formatter = logging.Formatter(
            "{asctime} - {levelname} - {message}", style="{", datefmt="%Y-%m-%d %H:%M:%S")

        handler = logging.FileHandler(locust_logfile, encoding="utf-8")
        handler.setFormatter(formatter)

        self.logger = logging.getLogger('locust_logger')
        self.logger.setLevel(logging.DEBUG)

        # Avoid adding multiple handlers
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        self.logger.propagate = False
