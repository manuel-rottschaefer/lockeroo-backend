"""This module handles all config related tasks."""

import json

with open('src/config/locker_config.json', 'r', encoding='utf-8') as config_file:
    locker_config = json.load(config_file)
