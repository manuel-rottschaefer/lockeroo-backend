"""
This module contains the station router which handles all station related requests
"""

# Basics
from typing import List

# FastAPI
from fastapi import APIRouter

# Models
from src.models.session_models import SessionView
from src.models.station_models import StationView, StationMaintenance

# Services
from src.services import locker_services, station_services
from src.services.logging_services import logger
from src.services.mqtt_services import fast_mqtt
from src.services.exceptions import ServiceExceptions, handle_exceptions

# Create the router
stationRouter = APIRouter()


@stationRouter.get('/{call_sign}/discover',
                   response_model=List[StationView],
                   description="Get a list of all stations within a range of a given location")
@handle_exceptions(logger)
async def get_nearby_stations(
        lat: float, lon: float, radius: float, amount: int):
    """Return a list of station withing a given range of a location."""
    return await station_services.discover(lat, lon, radius, amount)


@stationRouter.get('/{call_sign}/details',
                   response_model=StationView,
                   description='Get detailed information about a station'
                   )
@handle_exceptions(logger)
async def get_station_details(call_sign: str) -> StationView:
    """Get detailed information about a station"""
    return await station_services.get_details(call_sign)


@stationRouter.get('/{call_sign}/lockers/overview', response_model=SessionView)
@handle_exceptions(logger)
async def get_locker_overview(call_sign: str) -> SessionView:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_overview(call_sign)


@stationRouter.post('/{call_sign}/maintenance/schedule',
                    response_model=StationMaintenance)
@handle_exceptions(logger)
async def create_scheduled_maintenance(call_sign: str) -> StationMaintenance:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_overview(call_sign)


@stationRouter.get('/{call_sign}/maintenance/next',
                   response_model=StationMaintenance)
@handle_exceptions(logger)
async def get_next_scheduled_maintenance(call_sign: str) -> StationMaintenance:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_overview(call_sign)

### MQTT Endpoints ###
# TODO: Improve station mqtt message validation


@fast_mqtt.subscribe('stations/+/terminal/confirm')
async def handle_terminal_mode_confirmation(
        _client, topic, payload, _qos, _properties):
    """Handle a confirmation from a station that it entered a mode at its terminal"""
    call_sign = topic.split('/')[1]
    mode = payload.decode('utf-8')

    if call_sign and mode:
        logger.debug(
            "Received confirmation that the terminal at station '{call_sign}' entered {mode} mode.")
        await station_services.handle_terminal_mode_confirmation(call_sign, mode)
    else:
        logger.info('Invalid station confirmation.')


@fast_mqtt.subscribe('stations/+/verification/report')
async def handle_station_verification_report(
        _client, topic, payload, _qos, _properties):
    """Handle a payment verification report from a station"""
    call_sign = topic.split('/')[1]
    card_id = payload.decode('utf-8')
    logger.debug(
        f"Received payment verification report for station '{call_sign}' with card id '{card_id}'.")

    await station_services.handle_terminal_action_report(call_sign)


@fast_mqtt.subscribe('stations/+/payment/report')
async def handle_station_payment_report(
        _client, topic, _payload, _qos, _properties):
    """Handle a payment report from a station"""
    call_sign = topic.split('/')[1]
    logger.debug(f"Received payment report from station '{call_sign}'.")

    await station_services.handle_terminal_action_report(call_sign)


@fast_mqtt.subscribe('stations/+/locker/+/report')
async def handle_station_lock_report(
        _client, topic, payload, _qos, _properties):
    """Handle a locker report from a station"""
    # Extract station callsign, locker index and locker state from topic
    if len(topic.split('/')) != 5:
        return

    # Import station and locker information
    station_code: str = topic.split('/')[1]
    locker_index: int = int(topic.split('/')[3])

    # Extract the report from the payload
    report: str = payload.decode('utf-8')

    logger.debug(
        (f"Received '{report.lower()}' report from locker '{locker_index}'"
         " at station '{station_code}'.")
    )

    if report == "UNLOCKED":
        await locker_services.handle_unlock_confirmation(station_code, locker_index)
    elif report == "LOCKED":
        await locker_services.handle_lock_report(station_code, locker_index)
    else:
        logger.info(ServiceExceptions.INVALID_LOCKER_STATE,
                    station=station_code, locker=locker_index)
