"""This module contains the delays for the different actions and stations in the simulation."""
from typing import Dict, List
import configparser
from dotenv import load_dotenv

from src.models.session_models import SessionState

load_dotenv('.env')

config = configparser.ConfigParser()
config.read('mocking/.env')


def get_delay_range(key) -> float:
    value = config.get('QUICK_TIMEOUTS', key).replace(' ', '')
    if value:
        return list(map(float, value.split(',')))
    return 0


ACTION_DELAYS: Dict[SessionState, List[float]] = {
    # Time to wait after the session has entered the state
    SessionState.CREATED: get_delay_range('CREATED'),
    SessionState.PAYMENT_SELECTED: get_delay_range('PAYMENT_SELECTED'),
    SessionState.VERIFICATION: get_delay_range('VERIFICATION'),
    SessionState.STASHING: get_delay_range('STASHING'),
    SessionState.ACTIVE: get_delay_range('ACTIVE'),
    SessionState.PAYMENT: get_delay_range('PAYMENT'),
    SessionState.RETRIEVAL: get_delay_range('RETRIEVAL'),
    SessionState.CANCELED: get_delay_range('CANCELED'),
}


STATION_DELAYS: Dict[SessionState, List[int]] = {
    SessionState.VERIFICATION: [1, 3],
    SessionState.PAYMENT: [1, 3]
}
