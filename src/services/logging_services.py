"""
Lockeroo.logging_services
-------------------------
This module provides a unified, custom logging service

Key Features:
    - Initiates a logging session under a wrapper class
    - Provides automated logging setup

Dependencies:
    - fastapi
"""
# Basics
from datetime import datetime
from pathlib import Path
# FastAPI
from fastapi import HTTPException
# Logging
from loguru import logger


class LoggingService:
    """Provides the logging service for the application."""
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.logger = logger
            LoggingService._initialized = True
            self._configure_logger()

    def _configure_logger(self):
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

        self.logger.remove()  # Remove default handler
        self.logger.add(
            log_dir / f"{datetime.today().strftime('%Y-%m-%d')}.log",
            rotation="1 day",
            format="{time:YYYY-MM-DD HH:mm:ss} - {level} - {message}",
            encoding="utf-8",
            level="DEBUG")

    def should_log(self, record):
        """Filter function to exclude HTTPException."""
        if record["exception"] and isinstance(record["exception"].exception, HTTPException):
            return False  # Exclude HTTPException
        return True  # Include other logs

    def trace(self, message: str):
        self.logger.trace(message)

    def debug(self, message: str, session_id: str = None):
        if session_id:
            self.logger.debug(f"'S{session_id}' - {message}")
        else:
            self.logger.debug(message)

    def info(self, message: str, session_id: str = None):
        if session_id:
            self.logger.info(f"'S{session_id}' - {message}")
        else:
            self.logger.info(message)

    def warning(self, message: str):
        self.logger.warning(message)

    def error(self, message: str):
        self.logger.error(message)

    def new_section(self):
        self.logger.info('-' * 64)


logger_service = LoggingService()
