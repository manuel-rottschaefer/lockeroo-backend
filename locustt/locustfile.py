"""Locust configuration file for testing the Lockeroo Backend."""
from os import getenv
from uuid import uuid4
from dotenv import load_dotenv
import paho.mqtt.client as mqttc

from locust import HttpUser, TaskSet, task, between
from locustt.locust_logger import LocustLogger

from locustt.behaviors import (
    RegularSession,
    AbandonAfterCreate,
    AbandonAfterPaymentSelection,
    AbandonDuringVerification,
    AbandonDuringStashing,
    AbandonDuringActive,
    AbandonDuringPayment,
    AbandonDuringRetrieval
)


# Load backend environment
load_dotenv('./environments/.env')

# Set up logging
locust_logger = LocustLogger().logger

# Connect to the mqtt client
mqtt_client = mqttc.Client(mqttc.CallbackAPIVersion.VERSION2)
mqtt_client.connect("localhost", 1883, 60)
mqtt_client.loop_start()  # Start the loop to keep the connection alive


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


user_management = UserManager()


class SessionTaskSet(TaskSet):
    """TaskSet for regular session behavior"""
    mqtt = mqtt_client
    logger = locust_logger
    user_id: str = user_management.get_available_user()
    headers: dict = {"user": user_id}
    endpoint: str = getenv('API_BASE_URL')
    ws_endpoint: str = getenv('API_WS_URL')
    station_callsign: str = 'MUCODE'

    @task(90)
    def regular_session_task(self):
        RegularSession(self).run()

    @task(2)
    def abandon_after_create(self):
        AbandonAfterCreate(self).run()

    @task(2)
    def abandon_after_payment_selection(self):
        AbandonAfterPaymentSelection(self).run()

    @task(2)
    def abandon_during_verification(self):
        AbandonDuringVerification(self).run()

    @task(1)
    def abandon_during_stashing(self):
        AbandonDuringStashing(self).run()

    @task(1)
    def abandon_during_active(self):
        AbandonDuringActive(self).run()

    @task(1)
    def abandon_during_payment(self):
        AbandonDuringPayment(self).run()

    @task(1)
    def abandon_during_retrieval(self):
        AbandonDuringRetrieval(self).run()


class LockerStationUser(HttpUser):
    host = getenv('API_BASE_URL')
    tasks = {SessionTaskSet: 1}
    wait_time = between(15, 30)
