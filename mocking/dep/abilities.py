"""Abilities for the locust user mocker"""
import json
import threading
from time import sleep
from os import getenv
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


# Initialize the user pool
user_pool = UserPool()

# Initialize the mqtt client
mqtt_client = mqttc.Client(mqttc.CallbackAPIVersion.VERSION2)
mqtt_client.connect("localhost", 1883, 60)
mqtt_client.loop_start()

# Initialize the logger once
locust_logger = LocustLogger().logger

QUEUE_EXPIRATION = 300


class MockingSession:
    """A session object for locust users."""

    def __init__(self, task_set: TaskSet, user: HttpUser):
        self.task_set: TaskSet = task_set
        self.user_id: Optional[str] = None
        self.headers: dict
        self.logger = locust_logger
        self.client: HttpUser = user.client
        self.mqtt_client: mqttc.Client = mqtt_client
        self.endpoint: str = getenv('API_BASE_URL')
        self.ws_endpoint: str = getenv('API_WS_URL')
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
        lower = ACTION_DELAYS[session_state][0]
        upper = ACTION_DELAYS[session_state][1]
        sleep_duration = lower + (upper - lower) * (random() ** 3)
        sleep(sleep_duration)

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

    def terminate_session(self, invalid_status=False):
        """Terminate the current session and free up the user ID."""
        sleep(5)  # Wait five seconds before freeing up the user ID
        if self.session.id == None:
            self.session = {'id': 'Unknown'}
        if self.res.status_code == 422:
            self.logger.error(
                "Failed to terminate session due to request error.")
        elif invalid_status:
            self.logger.error((
                f"Terminating session '#{self.session.id}' "
                f"due to invalid status code."))
        else:
            self.logger.debug((
                f"Terminating session '#{self.session.id}' of "
                f"user {self.user_id}"))
        user_pool.drop_user(self.user_id)
        self.task_set.interrupt()

    ########################
    ###   USER ACTIONS   ###
    ########################

    def choose_station(self):
        """Request a list of stations from the backend and choose a random one."""
        self.res = self.client.get(
            f'{self.endpoint}/stations/', timeout=3
        )
        if self.res.status_code != 200:
            self.logger.error(f"Invalid status code '{self.res.status_code}' "
                              f" for station info request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()
        avail_station_codes: List[str] = [
            station['callsign'] for station in self.res.json()
        ]
        if len(avail_station_codes):
            self.station_callsign = choice(avail_station_codes)
        # self.logger.debug(f"Selected {self.station_callsign} as station.")

    def find_available_locker(self) -> Optional[str]:
        """Try to find an available locker at the locker station."""
        self.res = self.client.get(
            f'{self.endpoint}/stations/{self.station_callsign}/lockers', timeout=3)
        if self.res.status_code != 200:
            self.logger.error(f"Invalid status code '{self.res.status_code}' "
                              f" for locker info request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()
        avail_locker_types: List[LockerTypeAvailabilityView] = [
            LockerTypeAvailabilityView(**i) for i in self.res.json() if i['is_available']]
        if not avail_locker_types:
            # Wait here so a locker can become available
            self.terminate_session()

        if len(avail_locker_types):
            chosen_locker_type = choice(
                [locker_type.locker_type for locker_type in avail_locker_types])
            # self.logger.debug(
            #    f"Selected locker type {
            #        chosen_locker_type} from available lockers.")
            return chosen_locker_type

    def user_request_reservation(self) -> None:
        """Request a session reservation at the station."""
        locker_type = self.find_available_locker()
        self.res = self.client.post(
            self.endpoint + f'/stations/{self.station_callsign}/reservation',
            params={'locker_type': locker_type
                    }, headers=self.headers, timeout=3)
        if self.res.status_code != 202:
            self.logger.error(f"Invalid status code '{self.res.status_code}' "
                              f" for reservation request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()
        self.logger.info((
            f"Requested 'RESERVATION' for user '{self.user_id}' "
            f"at station '{self.station_callsign}'."))
        self.has_reservation = True

    def user_request_session(self, select_payment: bool = True) -> None:
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
        if self.res.status_code != 201:
            self.logger.error(f"Invalid status code '{self.res.status_code}' "
                              f" for creation request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()

        self.session = CreatedSessionView(**self.res.json())
        self.subscribe_to_updates()
        self.logger.info(
            f"Requested session '#{self.session.id}' for user "
            f"'#{self.user_id}' of behavior "
            f"{self.__class__.__name__} at station '{self.station_callsign}'.")

    def user_request_cancel_session(self) -> None:
        """Try to cancel a session."""
        self.res = self.client.patch(
            f'{self.endpoint}/sessions/{self.session.id}/cancel',
            headers=self.headers, timeout=3)
        if self.res.status_code != 202:
            self.logger.error(f"Invalid status code '{self.res.status_code}' "
                              f" for cancel request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()
        self.session = ConcludedSessionView(**self.res.json())
        self.logger.info((
            f"Requested cancelation of session '#{self.session.id}' at "
            f"station '{self.station_callsign}'."))

    def user_select_payment_method(self) -> None:
        """Try to select a payment method for a session."""
        self.res = self.client.put(
            f'{self.endpoint}/payments/{self.session.id}/method/select', params={
                'payment_method': self.payment_method.value
            }, headers=self.headers, timeout=3)
        if self.res.status_code != 202:
            self.logger.error(
                "Invalid status code for payment selection request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()
        self.session = ActiveSessionView(**self.res.json())
        self.logger.info(
            (f"Selected 'PAYMENT' method for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

    def user_request_verification(self) -> None:
        """Try to request verification for a session."""
        self.res = self.client.patch(
            f'{self.endpoint}/payments/{self.session.id}/verification/initiate',
            headers=self.headers, timeout=3)
        if self.res.status_code != 202:
            self.logger.error(f"Invalid status code '{self.res.status_code}' "
                              f" for verification request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()

        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Requested 'VERIFICATION' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

    def user_request_hold(self) -> None:
        """Try to request a session hold."""
        self.res = self.client.patch(
            f'{self.endpoint}/sessions/{self.session.id}/hold',
            headers=self.headers, timeout=3)
        if self.res.status_code != 202:
            self.logger.error(f"Invalid status code '{self.res.status_code}' "
                              f"for hold request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()
        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Requested 'HOLD' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

    def user_request_payment(self) -> None:
        """Try to request payment for a session."""
        self.res = self.client.patch(
            f'{self.endpoint}/payments/{self.session.id}/initiate',
            headers=self.headers, timeout=3)
        if self.res.status_code != 202:
            self.logger.error(
                "Invalid status code for payment initiation request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()
        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Requested 'PAYMENT' for session '#{self.session.id}' "
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

    ########################
    ###  STRIPE ACTIONS  ###
    ########################

    def stripe_report_verification(self):
        """Report a successfull stripe verification"""
        self.res = self.client.put(
            f'{self.endpoint}/payments/{self.session.id}/verification/complete',
            headers=self.headers, timeout=3)
        if self.res.status_code != 202:
            self.logger.error(f"Invalid status code '{self.res.status_code}' "
                              f" for verification request.")
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()
        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Completed 'VERIFICATION' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))

    def stripe_report_payment(self):
        """Report a successfull stripe payment"""
        self.res = self.client.patch(
            f'{self.endpoint}/payments/{self.session.id}/complete',
            headers=self.headers, timeout=3)
        if self.res.status_code != 202:
            self.terminate_session(invalid_status=True)
        self.res.raise_for_status()
        self.session = SessionView(**self.res.json())
        self.logger.info(
            (f"Completed 'PAYMENT' for session '#{self.session.id}' "
             f"at station '{self.station_callsign}'."))
