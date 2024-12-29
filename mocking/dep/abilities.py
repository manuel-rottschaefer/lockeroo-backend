"""Abilities for the locust user mocker"""
import json
import threading
from os import getenv
from time import sleep
from random import choice, uniform
from datetime import datetime, timedelta

from typing import List, Optional, Union

import paho.mqtt.client as mqttc
import websockets.sync.client as sync_websockets
from locust import HttpUser, TaskSet

from mocking.dep.mocking_logger import LocustLogger
from mocking.dep.delays import ACTION_DELAYS
from mocking.dep.user_pool import UserPool
from src.models.locker_models import LockerTypeAvailability
from src.models.session_models import (
    PaymentTypes,
    SessionView,
    ActiveSessionView,
    CreatedSessionView,
    ConcludedSessionView,
    SessionState,
    WebsocketUpdate,
    SESSION_TIMEOUTS)

# Initialize the user pool
user_pool = UserPool()

# Initialize the mqtt client
mqtt_client = mqttc.Client(mqttc.CallbackAPIVersion.VERSION2)
mqtt_client.connect("localhost", 1883, 60)
mqtt_client.loop_start()

# Initialize the logger once
locust_logger = LocustLogger().logger


class MockingSession:
    """A session object for locust users."""

    def __init__(self, task_set: TaskSet, user: HttpUser):
        self.task_set: TaskSet = task_set
        self.logger = locust_logger  # Reuse the initialized logger
        self.client: HttpUser = user.client
        self.mqtt_client: mqttc.Client = mqtt_client
        self.station_callsign = "MUCODE"
        self.payment_method = 'terminal'
        self.endpoint: str = getenv('API_BASE_URL')
        self.ws_endpoint: str = getenv('API_WS_URL')
        self.session: Union[CreatedSessionView, SessionView]
        self.user_id: Optional[str] = None
        self.headers: dict

        self.awaited_state: Optional[SessionState] = None

    def subscribe_to_updates(self):
        """Subscribe to a session update stream and handle awaited states."""
        ws_url = (f'{self.ws_endpoint}/sessions/{self.session.id}/subscribe?'
                  f'user_id={self.user_id}&session_token={self.session.websocket_token}')

        def monitor():
            with sync_websockets.connect(ws_url) as ws:
                while True:
                    msg = ws.recv()
                    update: WebsocketUpdate = WebsocketUpdate(
                        **json.loads(msg))
                    self.session.session_state = update.session_state

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    def await_state(self, state: SessionState, timeout: int = 300) -> None:
        """Wait for the next state to be reached."""
        expiration = datetime.now() + timedelta(seconds=timeout)
        try:
            while datetime.now() < expiration:
                if self.session.session_state == state:
                    self.logger.info(
                        f"Session '#{self.session.id}' reached state '{state}'.")
                    return
                sleep(0.2)
            self.logger.warning(
                f"Session '#{self.session.id}' did not reach state '{state}'.")
        except KeyboardInterrupt:
            return

    def delay_action(self, session_state: SessionState):
        """Emulate a user delay based on the session state.
        The delay should be less than the session timeout."""
        sleep(uniform(ACTION_DELAYS[session_state]
              [0], ACTION_DELAYS[session_state][1]))

    def wait_for_timeout(self, session_state: SessionState):
        """Let the user wait for the session timeout to expire.
        One second is added to the timeout to ensure the session actually expires."""
        sleep(SESSION_TIMEOUTS[session_state] + 1)

    def log_unexpected_state(self, session, state):
        self.logger.warning(
            f"Session '#{session.id}' is in state '{
                session.session_state}', "
            f"expected '{state}'.")

    def verify_state(self, expected_state):
        if self.session.session_state != expected_state:
            self.log_unexpected_state(self.session, expected_state)
            self.terminate_session()

    def terminate_session(self):
        user_pool.return_user(self.user_id)
        self.task_set.interrupt()

    ########################
    ###   USER ACTIONS   ###
    ########################

    def find_available_locker(self) -> Optional[str]:
        """Try to find an available locker at the locker station."""
        # Make the request
        res = self.client.get(
            self.endpoint + f'/stations/{self.station_callsign}/lockers', timeout=3)
        # Check for server errors
        if res.status_code == 400:
            self.terminate_session()
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        avail_locker_types: List[LockerTypeAvailability] = [
            LockerTypeAvailability(**i) for i in res.json() if i['is_available']]
        if not avail_locker_types:
            # Wait here so a locker can become available
            sleep(5)
            self.terminate_session()
            return None
        return choice([locker_type.locker_type for locker_type in avail_locker_types])

    def user_request_session(self) -> None:
        """Try to request a new session at the locker station."""
        # Make the request
        self.user_id = user_pool.get_available_user()
        if self.user_id is None:
            self.terminate_session()
            return None
        self.headers: dict = {"user": self.user_id}
        locker_type = self.find_available_locker()
        res = self.client.post(
            self.endpoint + '/sessions/create', params={
                'station_callsign': self.station_callsign,
                'locker_type': locker_type
            }, headers=self.headers, timeout=3)
        # Check for server errors
        if res.status_code == 400:
            # interrupt task set
            self.terminate_session()
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        self.session = CreatedSessionView(**res.json())
        if self.session.session_state != SessionState.CREATED:
            self.log_unexpected_state(self.session, SessionState.CREATED)
        # Subscribe to updates
        self.subscribe_to_updates()
        # Return obtained session
        self.logger.info(
            (f"Created session '#{self.session.id}' "
             f"with behavior {self.__class__.__name__}."))

    def user_request_cancel_session(self) -> None:
        """Try to cancel a session."""
        # Make the request
        res = self.client.put(
            self.endpoint + f'/sessions/{self.session.id}/cancel', headers=self.headers, timeout=3)
        # Check for server errors
        if res.status_code == 400:
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        print(res.json())
        self.session = ConcludedSessionView(**res.json())
        if self.session.session_state != SessionState.CANCELED:
            self.log_unexpected_state(self.session, SessionState.CANCELED)
        # Return current session
        self.logger.info(f"Canceled session '#{self.session.id}'.")

    def user_select_payment_method(self) -> None:
        """Try to select a payment method for a session."""
        payment_method = PaymentTypes.TERMINAL
        # Make the request
        res = self.client.put(
            self.endpoint + f'/sessions/{self.session.id}/payment/select', params={
                'payment_method': payment_method.value
            }, headers=self.headers, timeout=3)
        # Check for server errors
        if res.status_code == 400:
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        self.session = ActiveSessionView(**res.json())
        if self.session.session_state != SessionState.PAYMENT_SELECTED:
            self.log_unexpected_state(
                self.session, SessionState.PAYMENT_SELECTED)
        # Return current session
        self.logger.info((f"Selected {payment_method} for session "
                          f"'#{self.session.id}'."))

    def user_request_verification(self) -> None:
        """Try to request verification for a session."""
        # Make the request
        res = self.client.put(
            f'{self.endpoint}/sessions/{self.session.id}/payment/verify',
            headers=self.headers, timeout=3)
        # Check for server errors
        if res.status_code == 400:
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        self.session = SessionView(**res.json())
        # Return current session
        self.logger.info((f"Requested verification for session "
                          f"'#{self.session.id}'."))

    def request_payment(self) -> None:
        """Try to request payment for a session."""
        # Make the request
        res = self.client.put(
            f'{self.endpoint}/sessions/{self.session.id}/payment',
            headers=self.headers, timeout=3)
        # Check for server errors
        if res.status_code == 400:
            return None
        res.raise_for_status()
        # Check if the session state matches the expected state
        self.session = SessionView(**res.json())
        # Return current session
        self.logger.info((f"Requested payment for session "
                         f"'#{self.session.id}'."))

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
            f"{self.session.locker_index}/report'"), 'UNLOCKED', qos=2)
        self.logger.info((
            f"Locker {self.session.locker_index} opened "
            f"at station '{self.station_callsign}'."))

    def station_report_locker_close(self):
        self.mqtt_client.publish((
            f"stations/{self.station_callsign}/locker/"
            f"{self.session.locker_index}/report"), 'LOCKED', qos=2)
        self.logger.info((
            f"Locker {self.session.locker_index} closed "
            f"at station '{self.station_callsign}'."))
