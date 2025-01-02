"""This module contains the delays for the different actions and stations in the simulation."""
from dotenv import load_dotenv
import configparser
from typing import Dict, List

from src.models.session_models import SessionState

# This is extremely dumb, but it works
load_dotenv('.env')

config = configparser.ConfigParser()
config.read('mocking/.env')


def get_delay_ranges(key):
    value = config.get('QUICK_TIMEOUTS', key).replace(' ', '')
    if value:
        return list(map(float, value.split(',')))
    return None


ACTION_DELAYS: Dict[SessionState, List[float]] = {
    # Time to wait after the session has entered the state
    SessionState.CREATED: get_delay_ranges('CREATED'),
    SessionState.PAYMENT_SELECTED: get_delay_ranges('PAYMENT_SELECTED'),
    SessionState.VERIFICATION: get_delay_ranges('VERIFICATION'),
    SessionState.STASHING: get_delay_ranges('STASHING'),
    SessionState.ACTIVE: get_delay_ranges('ACTIVE'),
    SessionState.PAYMENT: get_delay_ranges('PAYMENT'),
    SessionState.RETRIEVAL: get_delay_ranges('RETRIEVAL'),
    SessionState.CANCELED: get_delay_ranges('CANCELED'),
}


STATION_DELAYS: Dict[SessionState, List[int]] = {
    SessionState.VERIFICATION: [1, 3],
    SessionState.PAYMENT: [1, 3]
}
