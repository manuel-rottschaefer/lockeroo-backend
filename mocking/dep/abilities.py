"""Abilities for the locust user mocker"""
import json
import threading
import configparser
from time import sleep
from random import choice, random
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
    PaymentMethod,
    SessionView,
    ActiveSessionView,
    CreatedSessionView,
    ConcludedSessionView,
    SessionState,
    WebsocketUpdate,
    SESSION_TIMEOUTS)

from src.exceptions.session_exceptions import InvalidSessionStateException

base_config = configparser.ConfigParser()
base_config.read('.env')

locust_config = configparser.ConfigParser()
locust_config.read('mocking/.env')

# Initialize the user pool
user_pool = UserPool()

# Initialize the mqtt client
mqtt_client = mqttc.Client(mqttc.CallbackAPIVersion.VERSION2)
mqtt_client.connect("localhost", 1883, 60)
mqtt_client.loop_start()

# Initialize the logger once
locust_logger = LocustLogger().logger

QUEUE_EXPIRATION = 300


class InvalidResCodeException(Exception):
    """Exception raised when a session is not matching the expected state."""

    def __init__(
        self,
            session_id: str = '',
            expected_code: int = 200,
            actual_code: int = 500):
        self.session_id = session_id
        self.expected_code = expected_code
        self.actual_code = actual_code

    def __str__(self):
        return (f"Invalid backend response code for session '{self.session_id}': "
                f"Expected {self.expected_code}, got {self.actual_code}")


class MockingSession:
    """A session object for locust users."""

    def __init__(self, task_set: TaskSet, user: HttpUser):
        self.task_set: TaskSet = task_set
        self.user_id: Optional[str] = None
        self.headers: dict
        self.logger = locust_logger
        self.client: HttpUser = user.client
        self.mqtt_client: mqttc.Client = mqtt_client
        self.endpoint: str = base_config.get(
            'ENDPOINTS', 'API_BASE_URL')
        self.ws_endpoint: str = base_config.get(
            'ENDPOINTS', 'API_WS_URL')
        self.session: Union[
            CreatedSessionView, SessionView,
            ConcludedSessionView]
        self.awaited_state: Optional[SessionState] = None
        self.station_callsign: Optional[str] = None
        self.payment_method: PaymentMethod
        self.has_reservation: bool = False
        self.session = None
        self.res: dict

        # Initialization
        self.choose_station()
        self.choose_payment_method()
        self.choose_user()

    ########################
    ###   GENERIC TOOLS  ###
    ########################

    def set_payment_method(self, method: PaymentMethod):
        self.payment_method = method

    def choose_payment_method(self) -> None:
        self.payment_method = PaymentMethod.TERMINAL

    def choose_user(self) -> None:
        self.user_id = user_pool.pick_user()
        if self.user_id is None:
            self.terminate_session()
        self.headers: dict = {"user": self.user_id}

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

    @handle_invalid_state
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
        lower = ACTION_DELAYS[session_state][0]
        upper = ACTION_DELAYS[session_state][1]
        sleep_duration = lower + (upper - lower) * (random() ** 3)
        # print(f"Delaying for {sleep_duration} seconds.")
        sleep(sleep_duration)

    @handle_invalid_state
    def wait_for_timeout(self, session_state: SessionState):
        """Let the user wait for the session timeout to expire.
        One second is added to the timeout to ensure the session actually expires."""
        if locust_config.get("TESTING_MODE", "MODE") == "NORMAL":
            sleep(SESSION_TIMEOUTS[session_state] + 1)
        else:
            sleep(6)

    def verify_state(self, expected_state, final=False):
        """Verify the current session state."""
        if self.session is None:
            self.logger.warning(
                "Could not verify state for session that was not created.")
            return
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
        """Terminate the current session and free up the user ID."""
        sleep(5)  # Wait five seconds before freeing up the user ID

        # if self.session is None:
        #    self.logger.warning(
        #        "Could not terminate session that was not created.")
        if self.session is not None:
            self.logger.debug((
                f"Terminating session '#{self.session.id}' of "
                f"user {self.user_id}"))
        user_pool.drop_user(self.user_id)
        self.task_set.interrupt()

    ########################
    ###   USER ACTIONS   ###
    ########################

    def choose_station(self, expected_code=200):
        """Request a list of stations from the backend and choose a random one."""
        self.res = self.client.get(
            f'{self.endpoint}/stations/', timeout=3
        )
        if self.res.status_code != expected_code:
            self.logger.error(f"Invalid status code '{self.res.status_code}'"
                              f" for station info request.")
            self.terminate_session()

        avail_station_codes: List[str] = [
            station['callsign'] for station in self.res.json()
        ]
        if len(avail_station_codes):
            self.station_callsign = choice(avail_station_codes)
        else:
            self.logger.warning("No stations available.")

    def find_available_locker(
            self, expected_code=200) -> Optional[str]:
        """Try to find an available locker at the locker station."""
        self.res = self.client.get(
            f'{self.endpoint}/stations/{self.station_callsign}/lockers', timeout=3)
        if self.res.status_code != expected_code:
            self.logger.error(f"Invalid status code '{self.res.status_code}' "
                              f" for locker find request.")
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code
            )

        avail_locker_types: List[LockerTypeAvailabilityView] = [
            LockerTypeAvailabilityView(**i) for i in self.res.json() if i['is_available']]
        if not avail_locker_types:
            # Wait here so a locker can become available
            self.logger.warning(
                f"No locker available at station '{self.station_callsign}'.")
            self.terminate_session()

        if len(avail_locker_types):
            chosen_locker_type = choice(
                [locker_type.locker_type for locker_type in avail_locker_types])
            return chosen_locker_type

    def user_request_reservation(
            self, expected_code=202) -> None:
        """Request a session reservation at the station."""
        locker_type = self.find_available_locker()
        self.res = self.client.post(
            self.endpoint + f'/stations/{self.station_callsign}/reservation',
            params={'locker_type': locker_type
                    }, headers=self.headers, timeout=3)
        if self.res.status_code != expected_code:
            if self.res.status_code != 404:
                self.logger.error(f"Invalid status code '{self.res.status_code}' "
                                  f" for reservation request.")
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code)

        self.logger.info((
            f"Requested 'RESERVATION' for user '{self.user_id}' "
            f"at station '{self.station_callsign}'."))
        self.has_reservation = True

    def user_request_session(
            self, select_payment: bool = True,
            expected_code=201) -> None:
        """Try to request a new session at the locker station."""
        if self.has_reservation:
            self.logger.debug(
                f"Activating reservation for user '{self.user_id}'.")
        # self.logger.info('-' * 64)
        locker_type = self.find_available_locker()
        self.res = self.client.post(
            self.endpoint + '/sessions/create', params={
                'station_callsign': self.station_callsign,
                'locker_type': locker_type,
                'payment_method': self.payment_method if select_payment else None
            }, headers=self.headers, timeout=3)
        if self.res.status_code != expected_code:
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code)

        self.session = CreatedSessionView(**self.res.json())
        self.subscribe_to_updates()
        self.logger.info(
            f"Requested session '#{self.session.id}' for user "
            f"'#{self.user_id}' of behavior "
            f"{self.__class__.__name__} at station '{self.station_callsign}'.")

    def user_request_cancel_session(
            self, expected_code=202) -> None:
        """Try to cancel a session."""
        self.res = self.client.patch(
            f'{self.endpoint}/sessions/{self.session.id}/cancel',
            headers=self.headers, timeout=3)
        if self.res.status_code != expected_code:
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code)

        self.session = ConcludedSessionView(**self.res.json())
        self.logger.info((
            f"Requested cancelation of session '#{self.session.id}' at "
            f"station '{self.station_callsign}'."))

    def user_select_payment_method(
            self, expected_code=202) -> None:
        """Try to select a payment method for a session."""
        self.res = self.client.put(
            f'{self.endpoint}/payments/{self.session.id}/method/select', params={
                'payment_method': self.payment_method.value
            }, headers=self.headers, timeout=3)
        if self.res.status_code != expected_code:
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code)

        self.session = ActiveSessionView(**self.res.json())
        self.logger.info(
            (f"Selected 'PAYMENT' method for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

    def user_request_verification(
            self, expected_code=202) -> None:
        """Try to request verification for a session."""
        self.res = self.client.patch(
            f'{self.endpoint}/payments/{self.session.id}/verification/initiate',
            headers=self.headers, timeout=3)
        if self.res.status_code != expected_code:
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code)

        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Requested 'VERIFICATION' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

    def user_request_hold(
            self, expected_code=202) -> None:
        """Try to request a session hold."""
        self.res = self.client.patch(
            f'{self.endpoint}/sessions/{self.session.id}/hold',
            headers=self.headers, timeout=3)
        if self.res.status_code != expected_code:
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code)

        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Requested 'HOLD' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

    def user_request_payment(
            self, expected_code=202) -> None:
        """Try to request payment for a session."""
        self.res = self.client.patch(
            f'{self.endpoint}/payments/{self.session.id}/initiate',
            headers=self.headers, timeout=3)
        if self.res.status_code != expected_code:
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code)

        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Requested 'PAYMENT' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

    ########################
    ###  STRIPE ACTIONS  ###
    ########################

    def stripe_report_verification(
            self, expected_code=202) -> None:
        """Report a successfull stripe verification"""
        self.res = self.client.put(
            f'{self.endpoint}/payments/{self.session.id}/verification/complete',
            headers=self.headers, timeout=3)
        if self.res.status_code != expected_code:
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code)

        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Completed 'VERIFICATION' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

    def stripe_report_payment(
            self, expected_code=202) -> None:
        """Report a successfull stripe payment"""
        self.res = self.client.patch(
            f'{self.endpoint}/payments/{self.session.id}/complete',
            headers=self.headers, timeout=3)
        if self.res.status_code != expected_code:
            self.terminate_session()
            raise InvalidResCodeException(
                session_id=self.session.id,
                expected_code=expected_code,
                actual_code=self.res.status_code)

        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Completed 'PAYMENT' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

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
