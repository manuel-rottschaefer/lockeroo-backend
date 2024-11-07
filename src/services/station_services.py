'''
This module contains the services for the station model.
'''

# Basics
from datetime import datetime
from typing import List

# API services
from fastapi import HTTPException
from beanie.operators import In, Near

# Entities
from src.entities.station_entity import Station
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker
from src.entities.queue_entity import QueueItem

# Models
from src.models.locker_models import LockerModel
from src.models.session_models import SessionModel, SessionStates
from src.models.queue_models import QueueStates
from src.models.station_models import (StationLockers, StationModel, StationStates,
                                       StationView, TerminalStates, StationMaintenance)

# Services
from ..services.exceptions import ServiceExceptions
from ..services.logging_services import logger


async def discover(lat: float, lon: float, radius,
                   amount) -> List[StationView]:
    '''Return a list of stations within a given range around a location'''
    stations: List[StationView] = StationModel.find(
        Near(StationModel.location, lat, lon, max_distance=radius)
    ).limit(amount)
    # if not stations:
    #    logger.info(ServiceExceptions.STATION_NOT_FOUND)
    return stations


async def get_details(call_sign: str) -> StationView:
    '''Get detailed information about a station'''

    # Get station data from the database
    station = await StationModel.find_one(StationModel.call_sign == call_sign)

    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    return station


async def set_state(self: StationModel, station_state: StationStates):
    '''Update the state of a locker. No checks are performed here,
    as the request is assumed to be valid.'''
    self.station_state = station_state
    await self.replace()
    logger.info("Station %s state set to {\
            %s", self.call_sign, station_state.value)
    return self


async def get_locker_overview(call_sign: StationModel) -> StationLockers:
    '''Determine for each locker type if it is available at the given station'''

    # 1: Check whether the station exists
    station: Station = await Station().fetch(call_sign=call_sign)

    if not station:
        logger.warning("Station '%s' does not exist.", call_sign)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.STATION_NOT_FOUND.value)

    # 2: Create the object
    availability = StationLockers()

    # 3: Loop over each locker type to find the amount of lockers
    locker_types = ['small', 'medium', 'large']
    for locker_type in locker_types:
        locker_data = await LockerModel.find(
            LockerModel.station == call_sign.call_sign,
            LockerModel.lockerType.name == locker_type,
            # LockerModel.state == LockerStates.operational,
        ).to_list()

        availability[locker_type] = len(locker_data) != 0

    return availability


async def handle_terminal_action_report(call_sign: str) -> None:
    '''This handler processes reports of completed actions at a station.
        It verifies the authenticity of the report and then updates the state
        values for the station and the assigned session as well as notifies
        the client so that the user can proceed. '''
    # 1: Find station by call sign
    station: Station = await Station().fetch(call_sign=call_sign)
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND, station=call_sign)
        return

    # 2: Check wether the station is currently told to await an action
    accepted_terminal_states = [
        TerminalStates.VERIFICATION, TerminalStates.PAYMENT]
    if station.terminal_state not in accepted_terminal_states:
        logger.info(ServiceExceptions.INVALID_TERMINAL_STATE,
                    station=call_sign, detail=station.terminal_state)
        return

    # 3: Find the session that is awaiting verification / payment
    accepted_session_states = [
        SessionStates.VERIFICATION_PENDING, SessionStates.PAYMENT_PENDING]
    session: Session = Session(await SessionModel.find_one(
        SessionModel.assigned_station == station.id,
        In(SessionModel.session_state, accepted_session_states))
    )
    if not session.exists:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND, station=call_sign)
        return

    # 4: Find the locker that belongs to this session
    locker: Locker = await Locker().fetch(locker_id=session.assigned_locker)
    if not locker:
        logger.info(ServiceExceptions.LOCKER_NOT_FOUND,
                    locker=session.assigned_locker)

    # 5: Set terminal state to idle
    await station.set_terminal_state(TerminalStates.IDLE)

    # 6: Instruct the locker to open
    await locker.instruct_unlock()

    # 7: Create an action
    # TODO: here?

    # 7: Set the queue item to completed
    queue: QueueItem = await QueueItem().fetch(session_id=session.id)
    await queue.set_state(QueueStates.COMPLETED)


async def handle_terminal_mode_confirmation(call_sign: str, _mode: str):
    '''This handler processes reports of stations whose terminals entered an active state.
    It verifies the authenticity and then notifies the client about the new state.'''
    # 1: Get the station object
    station: StationModel = await StationModel.find_one(
        StationModel.call_sign == call_sign
    )
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND, call_sign)


### Maintenance Events ###
async def create_maintenance_event(call_sign: str,
                                   scheduled_ts: datetime,
                                   _assigned_person: str) -> StationMaintenance:
    '''Insert a maintenance event in the database.'''
    # TODO: Get station here
    # 1: Get the station object
    station: StationModel = await StationModel.find_one(
        StationModel.call_sign == call_sign
    )
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND, call_sign)

    maintenance: StationMaintenance = await StationMaintenance(
        station=station.id,
        scheduled=scheduled_ts
    ).insert()

    return maintenance
