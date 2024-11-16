"""This file is used to create a MQTT client instance."""

# Basics
import logging

# FastAPI
from fastapi_mqtt import FastMQTT, MQTTConfig

# Configure the logger
logging.getLogger("fastapi_mqtt").setLevel(logging.WARNING)
logging.getLogger("gmqtt.client").setLevel(logging.WARNING)
logging.getLogger("gmqtt.mqtt.utils").setLevel(logging.WARNING)
logging.getLogger("gmqtt.mqtt.package").setLevel(logging.WARNING)
logging.getLogger("gmqtt.mqtt.protocol").setLevel(logging.WARNING)

# Configure the MQTT Client
mqtt_config = MQTTConfig()
fast_mqtt = FastMQTT(config=mqtt_config)
