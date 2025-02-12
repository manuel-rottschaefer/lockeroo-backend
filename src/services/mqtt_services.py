"""This file is used to create a MQTT client instance."""
# Basics
import logging
import re
from functools import wraps
from typing import Any
# FastAPI
from fastapi_mqtt import FastMQTT, MQTTConfig
from gmqtt import Client as MQTTClient
# Logging
from src.services.logging_services import logger_service as logger


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
                logger.warning(f"Invalid parameter type: {e}")
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
mqtt_config = MQTTConfig(
    host="localhost",
    port=1883,
    keepalive=60,
    version=5,
    reconnect_retries=1,
    reconnect_delay=6
)
fast_mqtt = FastMQTT(config=mqtt_config)


@fast_mqtt.on_connect()
def connect(client: MQTTClient, _flags: int, _rc: int, _properties: Any):
    client.subscribe("/mqtt")  # subscribing mqtt topic
    # logger.debug(
    # f"Connected to MQTT Broker: {client}")


@fast_mqtt.on_disconnect()
def disconnect(_client: MQTTClient, _packet, _exc=None):
    logger.debug(
        "Disconnected from MQTT Broker.")
