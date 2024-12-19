"""Locust configuration file for testing the Lockeroo Backend."""
from os import getenv
from uuid import uuid4
from dotenv import load_dotenv
import paho.mqtt.client as mqttc

from locust import HttpUser, TaskSet, task, between
from locustt.behaviors import regular_session_behavior
from locustt.locust_logger import LocustLogger


# Load dotenv
load_dotenv('./environments/.env')

# Set up logging
locust_logger = LocustLogger().logger


class UserManager():
    """Provides locust with user IDs"""

    def __init__(self):
        self.userbase = [str(uuid4()) for _ in range(10)]
        self.available_users = self.userbase.copy()

    def get_available_user(self):
        user = self.available_users.pop()
        locust_logger.debug(f"User {user} retrieved from available users.")
        return user

    def return_user(self, user_id: uuid4):
        self.available_users.append(user_id)
        locust_logger.debug(f"User {user_id} returned to available users.")


class MQTTManager():
    """Provides locust with a single MQTT client to emulate station behavior"""

    def __init__(self):
        self.client = mqttc.Client(mqttc.CallbackAPIVersion.VERSION2)
        self.client.connect("localhost", 1883, 60)
        locust_logger.debug("MQTT client connected to localhost:1883")


user_management = UserManager()
mqtt_manager = MQTTManager()


class SessionTaskSet(TaskSet):
    """TaskSet for regular session behavior"""
    mqtt = mqtt_manager
    logger = locust_logger
    user_id: str = user_management.get_available_user()
    headers: dict = {"user": user_id}
    endpoint: str = getenv('API_BASE_URL')
    ws_endpoint: str = getenv('API_WS_URL')
    station_callsign: str = 'MUCODE'

    @task(1)
    def regular_session_task(self):
        regular_session_behavior(self)


class LockerStationUser(HttpUser):
    host = getenv('API_BASE_URL')
    tasks = {SessionTaskSet: 1}
    wait_time = between(15, 30)
