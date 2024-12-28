from os import getenv
from typing import Dict, List

from dotenv import load_dotenv

from src.models.session_models import SessionState

load_dotenv('locustt/environments/quick.env')


def get_delay_ranges(key):
    value = getenv(key).replace(' ', '')
    if value:
        return list(map(int, value.split(',')))
    return None


ACTION_DELAYS: Dict[SessionState, List[int]] = {
    # Time to wait after the session has entered the state
    SessionState.CREATED: get_delay_ranges('CREATED'),
    SessionState.PAYMENT_SELECTED: get_delay_ranges('PAYMENT_SELECTED'),
    SessionState.VERIFICATION: get_delay_ranges('VERIFICATION'),
    SessionState.STASHING: get_delay_ranges('STASHING'),
    SessionState.ACTIVE: get_delay_ranges('ACTIVE'),
    SessionState.PAYMENT: get_delay_ranges('PAYMENT'),
    SessionState.RETRIEVAL: get_delay_ranges('RETRIEVAL'),
}


STATION_DELAYS: Dict[SessionState, List[int]] = {
    SessionState.VERIFICATION: [1, 3],
    SessionState.PAYMENT: [1, 3]
}
