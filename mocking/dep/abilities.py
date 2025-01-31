"""Abilities for the locust user mocker"""
import json
import threading
import configparser
from os import getenv
from time import sleep
from random import choice, uniform
from datetime import datetime, timedelta

from typing import List, Optional, Union

import paho.mqtt.client as mqttc
import websockets.sync.client as sync_websockets
from websockets.exceptions import ConnectionClosedError
from locust import HttpUser, TaskSet

from mocking.dep.mocking_logger import LocustLogger
from mocking.dep.delays import ACTION_DELAYS
from mocking.dep.exceptions import handle_invalid_state
from mocking.dep.user_pool import UserPool
from src.models.locker_models import LockerTypeAvailabilityView
from src.models.session_models import (
    PaymentTypes,
    SessionView,
    ActiveSessionView,
    CreatedSessionView,
    ConcludedSessionView,
    SessionState,
    WebsocketUpdate,
    SESSION_TIMEOUTS)

from src.exceptions.session_exceptions import InvalidSessionStateException


# Initialize the user pool
user_pool = UserPool()

# Initialize the mqtt client
mqtt_client = mqttc.Client(mqttc.CallbackAPIVersion.VERSION2)
mqtt_client.connect("localhost", 1883, 60)
mqtt_client.loop_start()

# Initialize the logger once
locust_logger = LocustLogger().logger

# Read the expiration window
config = configparser.ConfigParser()
config.read('mocking/.env')
QUEUE_EXPIRATION = float(config.get('QUICK_TIMEOUTS', 'QUEUE'))


class MockingSession:
    """A session object for locust users."""

    def __init__(self, task_set: TaskSet, user: HttpUser):
        self.task_set: TaskSet = task_set
        self.logger = locust_logger  # Reuse the initialized logger
        self.client: HttpUser = user.client
        self.mqtt_client: mqttc.Client = mqtt_client
        self.station_callsign = "MUCODE"
        self.payment_method = PaymentTypes.TERMINAL
        self.endpoint: str = getenv('API_BASE_URL')
        self.ws_endpoint: str = getenv('API_WS_URL')
        self.session: Union[CreatedSessionView, SessionView]
        self.user_id: Optional[str] = None
        self.headers: dict

        self.awaited_state: Optional[SessionState] = None

    def get_user(self) -> None:
        self.user_id = user_pool.get_available_user()
        self.headers: dict = {"user": self.user_id}
        if self.user_id is None:
            self.terminate_session()

    def subscribe_to_updates(self):
        """Subscribe to a session update stream and handle awaited states."""
        ws_url = (f'{self.ws_endpoint}/sessions/{self.session.id}/subscribe?'
                  f'user_id={self.user_id}&session_token={self.session.websocket_token}')

        def monitor():
            with sync_websockets.connect(ws_url) as ws:
                while True:
                    try:
                        msg = ws.recv()
                        update: WebsocketUpdate = WebsocketUpdate(
                            **json.loads(msg))
                        self.session.session_state = update.session_state
                    except ConnectionClosedError:
                        break

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    @ handle_invalid_state
    def await_state(self, expected_state: SessionState, timeout: float = QUEUE_EXPIRATION) -> None:
        """Wait for the next state to be reached."""
        expiration = datetime.now() + timedelta(seconds=timeout)
        try:
            while datetime.now() < expiration:
                if self.session.session_state == expected_state:
                    self.logger.info(
                        f"Session '#{self.session.id}' reached state '{expected_state}'.")
                    return
                sleep(0.2)
            self.logger.warning(
                f"Session '#{self.session.id}' did not reach state '{expected_state}'.")
            self.terminate_session()
            raise InvalidSessionStateException(
                session_id=self.session.id,
                actual_state=self.session.session_state,
                expected_states=[expected_state]
            )

        except KeyboardInterrupt:
            return

    def delay_action(self, session_state: SessionState):
        """Emulate a user delay based on the session state.
        The delay should be less than the session timeout."""
        sleep(uniform(ACTION_DELAYS[session_state]
              [0], ACTION_DELAYS[session_state][1]))

    @ handle_invalid_state
    def wait_for_timeout(self, session_state: SessionState):
        """Let the user wait for the session timeout to expire.
        One second is added to the timeout to ensure the session actually expires."""
        sleep(SESSION_TIMEOUTS[session_state] + 1)

    def verify_state(self, expected_state, final=False):
        """Verify the current session state."""
        if self.session.session_state == expected_state:
            self.logger.debug(
                f"Session '#{self.session.id}' is in expected state '{expected_state}'.")
            if final:
                self.terminate_session()
        else:
            self.logger.warning(
                f"Session '#{self.session.id}' is in state '{
                    self.session.session_state}', "
                f"expected '{expected_state}'.")

            raise InvalidSessionStateException(
                session_id=self.session.id,
                actual_state=self.session.session_state,
                expected_states=[expected_state]
            )

    def terminate_session(self):
        user_pool.return_user(self.user_id)
        # self.task_set.interrupt()

    ########################
    ###   USER ACTIONS   ###
    ########################

    def find_available_locker(self) -> Optional[str]:
        """Try to find an available locker at the locker station."""
        res = self.client.get(
            f'{self.endpoint}/stations/{self.station_callsign}/lockers', timeout=3)
        if res.status_code == 400:
            self.terminate_session()
        res.raise_for_status()

        # Check if the session state matches the expected state
        avail_locker_types: List[LockerTypeAvailabilityView] = [
            LockerTypeAvailabilityView(**i) for i in res.json() if i['is_available']]
        if not avail_locker_types:
            # Wait here so a locker can become available
            sleep(5)
            self.terminate_session()

        return choice([locker_type.locker_type for locker_type in avail_locker_types])

    def user_request_reservation(self) -> None:
        """Request a session reservation at the station."""
        self.get_user()
        locker_type = self.find_available_locker()
        res = self.client.post(
            self.endpoint + f'/stations/{self.station_callsign}/reservation',
            params={'locker_type': locker_type
                    }, headers=self.headers, timeout=3)

        if res.status_code == 204:
            self.terminate_session()
        res.raise_for_status()

    def user_request_session(self, select_payment: bool = True) -> None:
        """Try to request a new session at the locker station."""
        # self.logger.info('-' * 64)
        self.get_user()
        locker_type = self.find_available_locker()
        res = self.client.post(
            self.endpoint + '/sessions/create', params={
                'station_callsign': self.station_callsign,
                'locker_type': locker_type,
                'payment_method': self.payment_method if select_payment else None
            }, headers=self.headers, timeout=3)

        if res.status_code == 400:
            self.terminate_session()
        res.raise_for_status()

        self.session = CreatedSessionView(**res.json())
        self.subscribe_to_updates()

        self.logger.info(
            f"Created session '#{self.session.id}' of behavior "
            f"{self.__class__.__name__} at station '{self.station_callsign}'.")

    def user_request_cancel_session(self) -> None:
        """Try to cancel a session."""
        self.logger.info(
            f"Canceling session '#{self.session.id}' at station '{self.station_callsign}'.")

        res = self.client.put(
            f'{self.endpoint}/sessions/{self.session.id}/cancel',
            headers=self.headers, timeout=3)
        if res.status_code == 400:
            self.terminate_session()
        res.raise_for_status()

        self.session = ConcludedSessionView(**res.json())

    def user_select_payment_method(self) -> None:
        """Try to select a payment method for a session."""
        self.logger.info(
            (f"Selecting payment method for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

        res = self.client.put(
            f'{self.endpoint}/sessions/{self.session.id}/payment/select', params={
                'payment_method': self.payment_method.value
            }, headers=self.headers, timeout=3)
        if res.status_code == 400:
            self.terminate_session()
        res.raise_for_status()

        self.session = ActiveSessionView(**res.json())

    def user_request_verification(self) -> None:
        """Try to request verification for a session."""
        self.logger.info(
            (f"Requesting 'VERIFICATION' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

        res = self.client.put(
            f'{self.endpoint}/sessions/{self.session.id}/payment/verify',
            headers=self.headers, timeout=3)
        if res.status_code == 400:
            self.terminate_session()
        res.raise_for_status()

        self.session = SessionView(**res.json())

    def user_request_payment(self) -> None:
        """Try to request payment for a session."""
        self.logger.info(
            (f"Requesting 'PAYMENT' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

        res = self.client.put(
            f'{self.endpoint}/sessions/{self.session.id}/payment',
            headers=self.headers, timeout=3)
        if res.status_code == 400:
            self.terminate_session()
        res.raise_for_status()

        self.session = SessionView(**res.json())

    #########################
    ###  STATION ACTIONS  ###
    #########################

    def station_report_verification(self):
        self.logger.info(
            (f"Reporting 'VERIFICATION' at station '{self.station_callsign}' "
             f"for session '#{self.session.id}''."))
        self.mqtt_client.publish(
            f'stations/{self.station_callsign}/verification/report', '123456', qos=2)

    def station_report_payment(self):
        self.logger.info(
            (f"Reporting 'PAYMENT' at station '{self.station_callsign}' "
             f"for session '#{self.session.id}''."))
        self.mqtt_client.publish(
            f'stations/{self.station_callsign}/payment/report', '123456', qos=2)

    def station_report_locker_open(self):
        self.logger.info(
            (f"Instructing station '{self.station_callsign}' to open locker "
             f"{self.session.locker_index} for session '#{self.session.id}'.")
        )
        self.mqtt_client.publish((
            f"stations/{self.station_callsign}/locker/"
            f"{self.session.locker_index}/report'"), 'UNLOCKED', qos=2)

    def station_report_locker_close(self):
        self.logger.info(
            (f"Instructing station '{self.station_callsign}' to close locker "
             f"{self.session.locker_index} for session '#{self.session.id}'.")
        )
        self.mqtt_client.publish((
            f"stations/{self.station_callsign}/locker/"
            f"{self.session.locker_index}/report"), 'LOCKED', qos=2)
