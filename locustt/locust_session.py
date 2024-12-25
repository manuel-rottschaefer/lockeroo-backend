import threading
from os import getenv
from random import choice, uniform
from time import sleep
from typing import Optional, Union

import paho.mqtt.client as mqttc
import websockets.sync.client as sync_websockets
from locust import HttpUser, TaskSet

from locustt.locust_logger import LocustLogger
from locustt.user_pool import UserPool
from src.models.session_models import SessionState, SessionView

# Initialize the user pool
user_pool = UserPool()

# Initialize the mqtt client
mqtt_client = mqttc.Client(mqttc.CallbackAPIVersion.VERSION2)
mqtt_client.connect("localhost", 1883, 60)
mqtt_client.loop_start()

# Initialize the logger once
locust_logger = LocustLogger().logger

LOCKER_TYPES = ['small', 'medium', 'large']


class LocustSession:
    """A session object for locust users."""

    def __init__(self, task_set: TaskSet, user: HttpUser):
        self.task_set: TaskSet = task_set
        self.logger = locust_logger  # Reuse the initialized logger
        self.client: HttpUser = user.client
        self.mqtt_client: mqttc.Client = mqtt_client
        self.station_callsign = "MUCODE"
        self.locker_type = choice(LOCKER_TYPES)
        self.payment_method = 'terminal'
        self.endpoint: str = getenv('API_BASE_URL')
        self.ws_endpoint: str = getenv('API_WS_URL')
        self.session: SessionView
        self.user_id: Optional[str] = None
        self.headers: dict

        self.awaited_state: Optional[SessionState] = None

    def subscribe_to_updates(self):
        """Subscribe to a session update stream and handle awaited states."""
        ws_url = self.ws_endpoint + f'/sessions/{self.session.id}/subscribe'

        def monitor():
            with sync_websockets.connect(ws_url) as ws:
                while True:
                    message = ws.recv()
                    self.session.session_state = message.lower()

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    def await_session_state(self, state: SessionState) -> None:
        """Wait for the next state to be reached."""
        try:
            while self.session.session_state != state.lower():
                sleep(0.1)
            self.logger.info(
                f"Session '#{self.session.id}' reached state '{state}'.")
        except KeyboardInterrupt:
            pass

    def delay_session(self, state: Union[list, int]):
        if isinstance(state, list):
            sleep(uniform(state[0], state[1]))
        elif isinstance(state, int):
            sleep(state)

    def log_unexpected_state(self, session, state):
        self.logger.warning(
            f"Session '#{session.id}' is in state '{
                session.session_state}', "
            f"expected '{state}'.")

    def verify_session_state(self, expected_state):
        if self.session.session_state != expected_state:
            self.logger.warning(
                f"Session '#{self.session.id}' is in state '{
                    self.session.session_state}', "
                f"expected '{expected_state}'.")

    def terminate_session(self):
        user_pool.return_user(self.user_id)
        self.task_set.interrupt()

    ########################
    ###   USER ACTIONS   ###
    ########################

    def user_request_session(self):
        """Try to request a new session at the locker station."""
        # Make the request
        self.user_id = user_pool.get_available_user()
        if self.user_id is None:
            self.terminate_session()
            return None
        self.headers: dict = {"user": self.user_id}
        res = self.client.post(
            self.endpoint + '/sessions/create', params={
                'station_callsign': self.station_callsign,
                'locker_type': self.locker_type
            }, headers=self.headers, timeout=3)
        # Check for server errors
        if res.status_code == 400:
            # interrupt task set
            self.terminate_session()
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        session = SessionView(**res.json())
        if session.session_state != SessionState.CREATED:
            self.log_unexpected_state(session, SessionState.CREATED)
        # Return obtained session
        self.logger.info(
            (f"Session '#{session.id}' created "
             f"with behavior {self.__class__.__name__}."))
        return session

    def user_select_payment_method(self):
        """Try to select a payment method for a session."""
        # Make the request
        res = self.client.put(
            self.endpoint + f'/sessions/{self.session.id}/payment/select', params={
                'payment_method': 'terminal'
            }, headers=self.headers, timeout=3)
        # Check for server errors
        if res.status_code == 400:
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        session = SessionView(**res.json())
        if session.session_state != SessionState.PAYMENT_SELECTED:
            self.log_unexpected_state(session, SessionState.PAYMENT_SELECTED)
        # Return current session
        self.logger.info(f"Payment method selected for session '#{
                         self.session.id}'.")
        return session

    def user_request_verification(self):
        """Try to request verification for a session."""
        # Make the request
        res = self.client.put(
            self.endpoint + f'/sessions/{self.session.id}/payment/verify', headers=self.headers, timeout=3)
        # Check for server errors
        if res.status_code == 400:
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        session = SessionView(**res.json())
        # Return current session
        self.logger.info(f"Verification requested for session '#{
                         self.session.id}'.")
        return session

    def request_payment(self):
        """Try to request payment for a session."""
        # Make the request
        res = self.client.put(
            self.endpoint + f'/sessions/{self.session.id}/payment', headers=self.headers, timeout=3)
        # Check for server errors
        if res.status_code == 400:
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        session = SessionView(**res.json())
        # Return current session
        self.logger.info(f"Payment requested for session '#{
                         self.session.id}'.")
        return session

    #########################
    ###  STATION ACTIONS  ###
    #########################

    def station_report_verification(self):
        self.mqtt_client.publish(
            f'stations/{self.station_callsign}/verification/report', '123456', qos=2)
        self.logger.info(f"Verification reported at station '#{
            self.station_callsign}'.")

    def station_report_payment(self):
        self.mqtt_client.publish(
            f'stations/{self.station_callsign}/payment/report', '123456', qos=2)
        self.logger.info(f"Payment reported at station '#{
                         self.station_callsign}'.")

    def station_report_locker_open(self):
        self.mqtt_client.publish((
            f"stations/{self.station_callsign}/locker/"
            f"{self.session.station_index}/report'"), 'UNLOCKED', qos=2)
        self.logger.info((
            f"Locker {self.session.station_index} opened "
            f"at station '{self.station_callsign}'."))

    def station_report_locker_close(self):
        self.mqtt_client.publish((
            f"stations/{self.station_callsign}/locker/"
            f"{self.session.station_index}/report"), 'LOCKED', qos=2)
        self.logger.info((
            f"Locker {self.session.station_index} closed "
            f"at station '{self.station_callsign}'."))
