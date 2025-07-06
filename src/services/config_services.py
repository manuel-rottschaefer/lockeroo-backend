"""
Lockeroo.config_services
-------------------------
This module provides a unified config import process

Key Features:
    - Imports configuration from a static .env file and exposes it to other modules

Dependencies:
    - configparser
"""

from configparser import ConfigParser
from pathlib import Path

cfg = ConfigParser()
cfg.read(Path(__file__).resolve().parent.parent.parent / ".env")
