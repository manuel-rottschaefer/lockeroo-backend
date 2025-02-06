"""This module contains the delays for the different actions and stations in the simulation."""
from typing import Dict, List
import configparser

from src.models.session_models import SessionState

locust_config = configparser.ConfigParser()
locust_config.read('mocking/.env')

backend_conf = configparser.ConfigParser()
backend_conf.read('.env')


def get_delay_range(key) -> List[float]:
    """This function returns a list of delay values for a given key."""
    mode = locust_config.get('TESTING_MODE', 'MODE')
    if mode == "QUICK":
        lower = locust_config.get('MINIMUM_DELAYS', "QUICK").replace(' ', '')
        return [float(lower), float(lower)+1.0]
    elif mode == "DEFAULT":
        lower = locust_config.get('MINIMUM_DELAYS', key).replace(' ', '')
        upper = backend_conf.get(
            'SESSION_STATE_EXPIRATIONS', key).replace(' ', '')
        return [float(lower), float((upper))]
    else:
        raise ValueError(f"Cannot find delay range for state '{key}'.")


ACTION_DELAYS: Dict[SessionState, List[float]] = {
    # Time to wait after the session has entered the state
    SessionState.CREATED: get_delay_range('CREATED'),
    SessionState.PAYMENT_SELECTED: get_delay_range('PAYMENT_SELECTED'),
    SessionState.VERIFICATION: get_delay_range('VERIFICATION'),
    SessionState.STASHING: get_delay_range('STASHING'),
    SessionState.ACTIVE: get_delay_range('ACTIVE'),
    SessionState.HOLD: get_delay_range('HOLD'),
    SessionState.PAYMENT: get_delay_range('PAYMENT'),
    SessionState.RETRIEVAL: get_delay_range('RETRIEVAL'),
    SessionState.CANCELED: get_delay_range('CANCELED'),
}


STATION_DELAYS: Dict[SessionState, List[int]] = {
    SessionState.VERIFICATION: [1, 3],
    SessionState.PAYMENT: [1, 3]
}
