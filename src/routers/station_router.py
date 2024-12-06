"""
This module contains the station router which handles all station related requests
"""

# Basics
from typing import List, Optional, Annotated

# FastAPI & Beanie
from fastapi import APIRouter, Path
from beanie import PydanticObjectId as ObjId

# Models
from src.models.station_models import StationView, StationStates, TerminalStates
from src.models.session_models import SessionView, SessionStates
from src.models.locker_models import LockerView

# Services
from src.services import locker_services, station_services
from src.services.logging_services import logger
from src.services.mqtt_services import fast_mqtt, validate_mqtt_topic
from src.services.exceptions import ServiceExceptions, handle_exceptions

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


@station_router.get('/{call_sign}/details',
                    response_model=StationView,
                    description='Get detailed information about a station.'
                    )
@handle_exceptions(logger)
async def get_station_details(
        call_sign: Annotated[str, Path(pattern='^[A-Z]{6}$')]) -> StationView:
    """Get detailed information about a station"""
    return await station_services.get_details(call_sign)


@station_router.get('/{call_sign}/active_session_count',
                    response_model=int,
                    description='Get the amount of currently active sessions at this station.'
                    )
@handle_exceptions(logger)
async def get_active_session_count(
        call_sign: Annotated[str, Path(pattern='^[A-Z]{6}$')]) -> StationView:
    """Get detailed information about a station"""
    return await station_services.get_active_session_count(call_sign)


@station_router.get('/{call_sign}/lockers/{locker_index}', response_model=LockerView)
@handle_exceptions(logger)
async def get_locker_by_index(
        call_sign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        locker_index: int) -> Optional[LockerView]:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_by_index(
        call_sign=call_sign,
        locker_index=locker_index
    )


@station_router.get('/{call_sign}/lockers/overview', response_model=SessionView)
@handle_exceptions(logger)
async def get_locker_overview(
        call_sign: Annotated[str, Path(pattern='^[A-Z]{6}$')],) -> SessionView:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_overview(call_sign)


@station_router.put('/{call_sign}/state', response_model=StationView)
@handle_exceptions(logger)
async def set_station_state(
        call_sign: Annotated[str, Path(pattern='^[A-Z]{6}$')],
        state: StationStates) -> StationView:
    """Set the high-level station state which indicates general availability."""
    return await station_services.set_station_state(
        call_sign=call_sign,
        station_state=state)


@station_router.patch('/{call_sign}/reset_queue', response_model=StationView)
@handle_exceptions(logger)
async def reset_station_queue(call_sign: Annotated[str, Path(pattern='^[A-Z]{6}$')]) -> StationView:
    """Reset the queue at the station. This is helpful if the queue is stale."""
    return await station_services.reset_queue(
        call_sign=call_sign
    )


@validate_mqtt_topic('stations/+/terminal/confirm', [ObjId])
@fast_mqtt.subscribe('stations/+/terminal/confirm')
async def handle_terminal_mode_confirmation(
        _client, topic, payload, _qos, _properties) -> None:
    """Handle a confirmation from a station that it entered a mode at its terminal"""
    call_sign = topic.split('/')[1]
    mode = payload.decode('utf-8')
    terminal_state: TerminalStates

    if not mode:
        logger.warning(
            f"Invalid station terminal report from station {call_sign}.")
        return

    if mode == 'VERIFICATION':
        terminal_state = TerminalStates.VERIFICATION
    elif mode == 'PAYMENT':
        terminal_state = TerminalStates.PAYMENT

    await station_services.handle_terminal_confirmation(call_sign, terminal_state)


@validate_mqtt_topic('stations/+/verification/report', [ObjId])
@fast_mqtt.subscribe('stations/+/verification/report')
async def handle_verification_report(
        _client, topic, payload, _qos, _properties) -> None:
    """Handle a payment verification report from a station"""
    call_sign = topic.split('/')[1]
    card_id = payload.decode('utf-8')

    if not card_id:
        logger.warning(
            f"Invalid station verification report from station {card_id}")
        return

    logger.debug(
        f"Station '{call_sign}' reported {SessionStates.VERIFICATION} with card '#{card_id}'.")

    await station_services.handle_action_report(
        call_sign=call_sign,
        expected_session_state=SessionStates.VERIFICATION,
        expected_terminal_state=TerminalStates.VERIFICATION,
    )


@validate_mqtt_topic('stations/+/payment/report', [ObjId])
@fast_mqtt.subscribe('stations/+/payment/report')
async def handle_station_payment_report(
        _client, topic, _payload, _qos, _properties) -> None:
    """Handle a payment report from a station"""
    call_sign = topic.split('/')[1]

    logger.info(f"Station '{call_sign}' reported {SessionStates.PAYMENT}.")

    await station_services.handle_action_report(
        call_sign=call_sign,
        expected_session_state=SessionStates.PAYMENT,
        expected_terminal_state=TerminalStates.PAYMENT
    )


@validate_mqtt_topic('stations/+/locker/+/report', [ObjId, int])
@fast_mqtt.subscribe('stations/+/locker/+/report')
async def handle_locker_report(
        _client, topic, payload, _qos, _properties) -> None:
    """Handle a locker report from a station"""

    # Import station and locker information
    call_sign: str = topic.split('/')[1]
    locker_index: int = int(topic.split('/')[3])

    if not locker_index:
        logger.warning(f"Invalid locker report from station {call_sign}.")
        return

    # Extract the report from the payload
    report: str = payload.decode('utf-8')
    if not report:
        return

    if report == "UNLOCKED":
        await locker_services.handle_unlock_confirmation(call_sign, locker_index)
    elif report == "LOCKED":
        await locker_services.handle_lock_report(call_sign, locker_index)
    else:
        # TODO: This needs a seperate exception, maybe even in a seperate ENUM
        logger.info(ServiceExceptions.INVALID_LOCKER_STATE,
                    station=call_sign, locker=locker_index)
