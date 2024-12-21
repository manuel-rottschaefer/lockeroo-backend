from src.models.session_models import SessionStates

from typing import Dict, List
from dotenv import load_dotenv
from os import getenv

load_dotenv('locustt/environments/quick.env')


def get_delay_ranges(key):
    value = getenv(key)
    if value:
        return list(map(int, value.split(',')))
    return None


ACTION_DELAYS: Dict[SessionStates, List[int]] = {
    # Time to wait after the session has entered the state
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
