from typing import Dict, List
from random import uniform, choice
from dotenv import load_dotenv
from os import getenv
from time import sleep

from locust import TaskSet
import locustt.user_abilities as user
import locustt.station_abilities as station

from src.models.session_models import SessionView, SessionStates, FOLLOW_UP_STATES

# Delay timeframe in seconds after each action
load_dotenv('locustt/environments/normal.env')


def get_delay_ranges(key):
    value = getenv(key)
    if value:
        return list(map(int, value.split(',')))
    return None


USER_DELAYS: Dict[SessionStates, List[int]] = {
    SessionStates.CREATED: get_delay_ranges('CREATED'),
    SessionStates.PAYMENT_SELECTED: get_delay_ranges('PAYMENT_SELECTED'),
    SessionStates.VERIFICATION: get_delay_ranges('VERIFICATION'),
    SessionStates.STASHING: get_delay_ranges('STASHING'),
    SessionStates.ACTIVE: get_delay_ranges('ACTIVE'),
    SessionStates.PAYMENT: get_delay_ranges('PAYMENT'),
    SessionStates.RETRIEVAL: get_delay_ranges('RETRIEVAL'),
}

STATION_DELAYS: Dict[SessionStates, List[int]] = {
    SessionStates.VERIFICATION: [1, 3],
    SessionStates.PAYMENT: [1, 3]
}

LOCKER_TYPES = ['small', 'medium', 'large']


class BaseBehavior:
    def __init__(self, task_set: TaskSet):
        self.task_set = task_set

    def sleep_for(self, state):
        sleep(uniform(*USER_DELAYS[state]))

    def await_next_state(self, session: SessionView):
        """Wait for the next state to be reached."""
        state = user.await_websocket_state(
            task_set=self.task_set,
            ws_endpoint=self.task_set.ws_endpoint,
            session_id=session.id,
            desired_state=FOLLOW_UP_STATES[session.session_state]
        )
        sleep(uniform(*USER_DELAYS[FOLLOW_UP_STATES[session.session_state]]))
        return SessionStates[state.upper()]

    def report_station_action(self, action, state, locker_number=None):
        getattr(station, action)(
            logger=self.task_set.logger,
            mqtt=self.task_set.mqtt,
            callsign=self.task_set.station_callsign,
            locker_number=locker_number
        )
        sleep(uniform(*STATION_DELAYS[state]))

    def create_session(self):
        if not (session := user.create_session(
            task_set=self.task_set,
            station_callsign=self.task_set.station_callsign,
            locker_type=choice(LOCKER_TYPES),
        )):
            self.task_set.interrupt()
        self.task_set.logger.info(
            (f"Created session '#{session.id}' "
             f"with '{self.__class__.__name__}' Behavior."))
        self.sleep_for(SessionStates.CREATED)
        return session

    def select_payment_method(self, session_id, payment_method):
        if not (session := user.select_payment_method(
            task_set=self.task_set,
            session_id=session_id,
            payment_method=payment_method
        )):
            self.task_set.interrupt()
        self.sleep_for(SessionStates.PAYMENT_SELECTED)
        return session

    def request_verification(self, session_id):
        if not (session := user.request_verification(
            task_set=self.task_set,
            session_id=session_id
        )):
            self.task_set.interrupt()
        self.sleep_for(SessionStates.VERIFICATION)
        return session

    def report_verification(self):
        station.report_verification(
            logger=self.task_set.logger,
            mqtt=self.task_set.mqtt,
            callsign=self.task_set.station_callsign
        )
        sleep(uniform(*STATION_DELAYS[SessionStates.VERIFICATION]))

    def request_payment(self, session_id):
        if not (session := user.request_payment(
            task_set=self.task_set,
            session_id=session_id
        )):
            self.task_set.interrupt()
        self.sleep_for(SessionStates.PAYMENT)
        return session

    def report_payment(self):
        station.report_payment(
            logger=self.task_set.logger,
            mqtt=self.task_set.mqtt,
            callsign=self.task_set.station_callsign
        )
        sleep(uniform(*STATION_DELAYS[SessionStates.PAYMENT]))

    def report_locker_open(self, locker_number: int, state: SessionStates):
        station.report_locker_open(
            logger=self.task_set.logger,
            mqtt=self.task_set.mqtt,
            callsign=self.task_set.station_callsign,
            locker_number=locker_number
        )
        self.sleep_for(state)

    def report_locker_close(self, locker_number: int, state: SessionStates = None):
        station.report_locker_close(
            logger=self.task_set.logger,
            mqtt=self.task_set.mqtt,
            callsign=self.task_set.station_callsign,
            locker_number=locker_number
        )
        if state:
            self.sleep_for(state)


class RegularSession(BaseBehavior):
    """Run a regular session."""

    def run(self):  # pylint: disable=missing-function-docstring
        session = self.create_session()
        session = self.select_payment_method(session.id, 'terminal')
        session = self.request_verification(session.id)
        session.session_state = self.await_next_state(session)
        self.report_verification()
        self.report_locker_open(session.locker_index, SessionStates.STASHING)
        self.report_locker_close(session.locker_index, SessionStates.ACTIVE)
        session = self.request_payment(session.id)
        session.session_state = self.await_next_state(session)
        self.report_payment()
        self.report_locker_open(session.locker_index, SessionStates.RETRIEVAL)
        self.report_locker_close(session.locker_index)


class AbandonAfterCreate(BaseBehavior):
    """Abandon session after creation."""

    def run(self):  # pylint: disable=missing-function-docstring
        _session = self.create_session()
        self.task_set.interrupt()


class AbandonAfterPaymentSelection(BaseBehavior):
    """Abandon session after payment selection."""

    def run(self):  # pylint: disable=missing-function-docstring
        session = self.create_session()
        session = self.select_payment_method(session.id, 'terminal')
        self.task_set.interrupt()


class AbandonDuringVerification(BaseBehavior):
    """Abandon session after verification report."""

    def run(self):  # pylint: disable=missing-function-docstring
        session = self.create_session()
        session = self.select_payment_method(session.id, 'terminal')
        session = self.request_verification(session.id)
        session.session_state = self.await_next_state(session)
        self.task_set.interrupt()


class AbandonDuringStashing(BaseBehavior):
    """Abandon session after locker open."""

    def run(self):  # pylint: disable=missing-function-docstring
        session = self.create_session()
        session = self.select_payment_method(session.id, 'terminal')
        session = self.request_verification(session.id)
        session.session_state = self.await_next_state(session)
        self.report_verification()
        self.report_locker_open(session.locker_index, SessionStates.STASHING)
        self.task_set.interrupt()


class AbandonDuringActive(BaseBehavior):
    """Abandon session after locker close."""

    def run(self):  # pylint: disable=missing-function-docstring
        session = self.create_session()
        session = self.select_payment_method(session.id, 'terminal')
        session = self.request_verification(session.id)
        session.session_state = self.await_next_state(session)
        self.report_verification()
        self.report_locker_open(session.locker_index, SessionStates.STASHING)
        self.report_locker_close(session.locker_index, SessionStates.ACTIVE)
        self.task_set.interrupt()


class AbandonDuringPayment(BaseBehavior):
    """Abandon session after payment request."""

    def run(self):  # pylint: disable=missing-function-docstring
        session = self.create_session()
        session = self.select_payment_method(session.id, 'terminal')
        session = self.request_verification(session.id)
        session.session_state = self.await_next_state(session)
        self.report_verification()
        self.report_locker_open(session.locker_index, SessionStates.STASHING)
        self.report_locker_close(session.locker_index, SessionStates.ACTIVE)
        session = self.request_payment(session.id)
        self.session_state = self.await_next_state(session)
        self.task_set.interrupt()


class AbandonDuringRetrieval(BaseBehavior):
    """Abandon session after payment report."""

    def run(self):  # pylint: disable=missing-function-docstring
        session = self.create_session()
        session = self.select_payment_method(session.id, 'terminal')
        session = self.request_verification(session.id)
        session.session_state = self.await_next_state(session)
        self.report_verification()
        self.report_locker_open(session.locker_index, SessionStates.STASHING)
        self.report_locker_close(session.locker_index, SessionStates.ACTIVE)
        session = self.request_payment(session.id)
        session.session_state = self.await_next_state(session)
        self.report_payment()
        self.report_locker_open(session.locker_index, SessionStates.RETRIEVAL)
        self.task_set.interrupt()
