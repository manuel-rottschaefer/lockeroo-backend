"""This file is used to create a MQTT client instance."""

# Basics
import logging
from functools import wraps
import re


# FastAPI
from fastapi_mqtt import FastMQTT, MQTTConfig

# Services
from src.services.logging_services import logger


def validate_mqtt_topic(pattern: str, param_types: list):
    """Validate an mqtt topic string and its contained data types."""
    def decorator(func):
        @wraps(func)
        async def wrapper(topic: str, *args, **kwargs):
            # Convert MQTT pattern to regex pattern
            regex_pattern = pattern.replace('+', '([^/]+)').replace('#', '.*')
            match = re.fullmatch(regex_pattern, topic)
            if not match:
                logger.warning(f"Invalid MQTT topic: {topic}")
                return

            # Extract parameters from the topic
            params = match.groups()

            # Convert parameters to specified types
            try:
                converted_params = [param_type(
                    param) for param, param_type in zip(params, param_types)]
            except ValueError as e:
                logger.warning(
                    f"Parameter conversion error for topic {topic}: {e}")
                return

            return await func(*converted_params, *args, **kwargs)
        return wrapper
    return decorator


# Configure the logger
logging.getLogger("fastapi_mqtt").setLevel(logging.WARNING)
logging.getLogger("gmqtt.client").setLevel(logging.WARNING)
logging.getLogger("gmqtt.mqtt.utils").setLevel(logging.WARNING)
logging.getLogger("gmqtt.mqtt.package").setLevel(logging.WARNING)
logging.getLogger("gmqtt.mqtt.protocol").setLevel(logging.WARNING)

# Configure the MQTT Client
mqtt_config = MQTTConfig()
fast_mqtt = FastMQTT(config=mqtt_config)
