"""
This module contains the station router which handles all station related requests
"""

# Basics
from typing import Annotated, List, Optional

from beanie import PydanticObjectId as ObjId
# FastAPI & Beanie
from fastapi import APIRouter, Path, Response

from src.models.locker_models import LockerView, LockerStates
from src.models.session_models import SessionStates, SessionView
# Models
from src.models.station_models import (StationStates, StationView,
                                       TerminalStates)
# Services
from src.services import locker_services, station_services
from src.services.exception_services import (ServiceExceptions,
                                             handle_exceptions)
import src.services.exception_services
from src.services.logging_services import logger
from src.services.mqtt_services import fast_mqtt, validate_mqtt_topic
# Exceptions
from src.exceptions.station_exceptions import InvalidStationReportException
from src.exceptions.locker_exceptions import InvalidLockerStateException

# Create the router
station_router = APIRouter()


@station_router.get('/discover',
                    response_model=List[StationView],
                    description="Get a list of all stations within a range of a given location.")
@handle_exceptions(logger)
async def get_nearby_stations(
        lat: float, lon: float, radius: float, amount: int):
    """Return a list of station withing a given range of a location."""
    return await station_services.discover(lat, lon, radius, amount)


@station_router.get('/{callsign}/details',
                    response_model=StationView,
                    description='Get detailed information about a station.'
                    )
@handle_exceptions(logger)
async def get_station_details(
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        response: Response) -> StationView:
    """Get detailed information about a station"""
    return await station_services.get_details(
        callsign=callsign, response=response)


@station_router.get('/{callsign}/active_session_count',
                    response_model=int,
                    description='Get the amount of currently active sessions at this station.'
                    )
@handle_exceptions(logger)
async def get_active_session_count(
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        response: Response) -> StationView:
    """Get detailed information about a station"""
    return await station_services.get_active_session_count(
        callsign=callsign, response=response)


@station_router.get('/{callsign}/lockers/{locker_index}', response_model=LockerView)
@handle_exceptions(logger)
async def get_locker_by_index(
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        locker_index: int,
        response: Response) -> Optional[LockerView]:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_by_index(
        callsign=callsign,
        locker_index=locker_index,
        response=response
    )


@station_router.get('/{callsign}/lockers/overview', response_model=SessionView)
@handle_exceptions(logger)
async def get_locker_overview(
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')]) -> SessionView:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_overview(
        callsign=callsign, response=Response)


@station_router.put('/{callsign}/state', response_model=StationView)
@handle_exceptions(logger)
async def set_station_state(
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        state: StationStates) -> StationView:
    """Set the high-level station state which indicates general availability."""
    return await station_services.set_station_state(
        callsign=callsign,
        station_state=state)


@station_router.patch('/{callsign}/reset_queue', response_model=StationView)
@handle_exceptions(logger)
async def reset_station_queue(
        callsign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        response: Response) -> StationView:
    """Reset the queue at the station. This is helpful if the queue is stale."""
    return await station_services.reset_queue(
        callsign=callsign,
        response=response
    )


@validate_mqtt_topic('stations/+/terminal/confirm', [ObjId])
@fast_mqtt.subscribe('stations/+/terminal/confirm')
async def handle_terminal_mode_confirmation(
        _client, topic, payload, _qos, _properties) -> None:
    """Handle a confirmation from a station that it entered a mode at its terminal"""
    callsign = topic.split('/')[1]
    mode = payload.decode('utf-8')
    terminal_state: TerminalStates

    if not mode:
        logger.warning(
            f"Invalid station terminal report from station {callsign}.")
        return

    if mode == 'VERIFICATION':
        terminal_state = TerminalStates.VERIFICATION
    elif mode == 'PAYMENT':
        terminal_state = TerminalStates.PAYMENT

    await station_services.handle_terminal_confirmation(callsign, terminal_state)


@validate_mqtt_topic('stations/+/verification/report', [ObjId])
@fast_mqtt.subscribe('stations/+/verification/report')
async def handle_verification_report(
        _client, topic, payload, _qos, _properties) -> None:
    """Handle a payment verification report from a station"""
    callsign = topic.split('/')[1]
    card_id = payload.decode('utf-8')

    # if not callsign or not card_id:
    #    raise src.services.exception_services.InvalidStationReportException(
    #        station_callsign=callsign,
    #        reported_state=SessionStates.VERIFICATION)

    logger.info(
        f"Station '{callsign}' reported {SessionStates.VERIFICATION} with card '#{card_id}'.")

    await station_services.handle_terminal_report(
        callsign=callsign,
        expected_session_state=SessionStates.VERIFICATION,
        expected_terminal_state=TerminalStates.VERIFICATION,
    )


@validate_mqtt_topic('stations/+/payment/report', [ObjId])
@fast_mqtt.subscribe('stations/+/payment/report')
async def handle_station_payment_report(
        _client, topic, _payload, _qos, _properties) -> None:
    """Handle a payment report from a station"""
    callsign = topic.split('/')[1]

    logger.info(f"Station '{callsign}' reported {
                SessionStates.PAYMENT} with card '#123456'.")

    await station_services.handle_terminal_report(
        callsign=callsign,
        expected_session_state=SessionStates.PAYMENT,
        expected_terminal_state=TerminalStates.PAYMENT
    )


@validate_mqtt_topic('stations/+/locker/+/report', [ObjId, int])
@fast_mqtt.subscribe('stations/+/locker/+/report')
async def handle_locker_report(
        _client, topic, payload, _qos, _properties) -> None:
    """Handle a locker report from a station"""

    # Import station and locker information
    callsign: str = topic.split('/')[1]
    locker_index: int = int(topic.split('/')[3])
    if not locker_index:
        logger.warning(f"Invalid locker report from station {callsign}.")
        return

    # Extract the report from the payload
    report: str = payload.decode('utf-8').lower()
    if not report:
        return

    # TODO: D
    if report == LockerStates.UNLOCKED:
        await locker_services.handle_unlock_confirmation(callsign, locker_index)
    elif report == LockerStates.LOCKED:
        await locker_services.handle_lock_report(callsign, locker_index)
    else:
        raise InvalidStationReportException(
            station_callsign=callsign, reported_state=report)
