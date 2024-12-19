from typing import Dict, List
from random import uniform, choice
from time import sleep

from locust import TaskSet
import locustt.user_abilities as user
import locustt.station_abilities as station

from src.models.session_models import SessionView, SessionStates

# Delay timeframe in seconds after each action
USER_DELAYS: Dict[SessionStates, List[int]] = {
    SessionStates.CREATED: [5, 9],
    SessionStates.PAYMENT_SELECTED: [5, 9],
    SessionStates.VERIFICATION: [5, 9],
    SessionStates.STASHING: [5, 9],
    SessionStates.ACTIVE: [5, 9],
    SessionStates.PAYMENT: [5, 9],
    SessionStates.RETRIEVAL: [5, 9]
}

STATION_DELAYS: Dict[SessionStates, List[int]] = {
    SessionStates.VERIFICATION: [1, 3],
    SessionStates.PAYMENT: [1, 3]
}

LOCKER_TYPES = ['small', 'medium', 'large']


def regular_session_behavior(task_set: TaskSet):
    """Run a regular session."""
    session: SessionView
    if not (session := user.create_session(
        task_set=task_set,
        station_callsign=task_set.station_callsign,
        locker_type=choice(LOCKER_TYPES),
    )):
        task_set.interrupt()
    sleep(uniform(*USER_DELAYS[SessionStates.CREATED]))

    session = user.select_payment_method(
        task_set=task_set,
        session_id=session.id,
        payment_method='terminal'
    )
    sleep(uniform(*USER_DELAYS[SessionStates.PAYMENT_SELECTED]))

    session = user.request_verification(
        task_set=task_set,
        session_id=session.id
    )

    user.await_websocket_state(
        task_set=task_set,
        ws_endpoint=task_set.ws_endpoint,
        session_id=session.id,
        desired_state='verification'
    )
    sleep(uniform(*USER_DELAYS[SessionStates.VERIFICATION]))

    station.report_verification(
        logger=task_set.logger,
        mqtt=task_set.mqtt.client,
        callsign=task_set.station_callsign
    )
    sleep(uniform(*STATION_DELAYS[SessionStates.VERIFICATION]))

    station.report_locker_open(
        logger=task_set.logger,
        mqtt=task_set.mqtt.client,
        callsign=task_set.station_callsign,
        locker_number=session.locker_index
    )
    sleep(uniform(*USER_DELAYS[SessionStates.STASHING]))

    station.report_locker_close(
        logger=task_set.logger,
        mqtt=task_set.mqtt.client,
        callsign=task_set.station_callsign,
        locker_number=session.locker_index
    )
    sleep(uniform(*USER_DELAYS[SessionStates.ACTIVE]))

    user.request_payment(
        task_set=task_set,
        session_id=session.id
    )

    user.await_websocket_state(
        task_set=task_set,
        ws_endpoint=task_set.ws_endpoint,
        session_id=session.id,
        desired_state='payment'
    )
    sleep(uniform(*USER_DELAYS[SessionStates.PAYMENT]))

    station.report_payment(
        logger=task_set.logger,
        mqtt=task_set.mqtt.client,
        callsign=task_set.station_callsign
    )
    sleep(uniform(*STATION_DELAYS[SessionStates.PAYMENT]))

    station.report_locker_open(
        logger=task_set.logger,
        mqtt=task_set.mqtt.client,
        callsign=task_set.station_callsign,
        locker_number=session.locker_index
    )
    sleep(uniform(*USER_DELAYS[SessionStates.RETRIEVAL]))

    station.report_locker_close(
        logger=task_set.logger,
        mqtt=task_set.mqtt.client,
        callsign=task_set.station_callsign,
        locker_number=session.locker_index
    )
