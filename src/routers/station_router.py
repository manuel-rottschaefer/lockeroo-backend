"""
Lockeroo.station_router
-------------------------
This module provides endpoint routing for station functionalities

Key Features:
    - Provides various station endpoints

Dependencies:
    - fastapi
    - beanie
"""
# Basics
from typing import Annotated, Any, List, Optional
from uuid import uuid4
# FastAPI & Beanie
from beanie import PydanticObjectId as ObjId
from fastapi import (
    APIRouter, Path, Response,
    Depends, Query, Header,
    status, HTTPException)
from lockeroo_models.locker_models import (
    LockerState,
    LockerView,
    LockerTypeAvailabilityView,
    LockerAvailabilityView)
# Entities
from src.entities.user_entity import User
# Models
from lockeroo_models.station_models import (
    StationDetailedView,
    StationLocationView,
    StationDashboardView,
    StationState, TerminalState)
from lockeroo_models.session_models import SessionState
# Services
from src.services.logging_services import logger_service as logger
from src.services.exception_services import handle_exceptions
from src.services.locker_services import LOCKER_TYPE_NAMES
from src.services import station_services, locker_services
from src.services.mqtt_services import fast_mqtt, validate_mqtt_topic
from src.services.auth_services import auth_check
# Exceptions
from src.exceptions.locker_exceptions import LockerNotAvailableException
from src.exceptions.locker_exceptions import InvalidLockerReportException

# Create the router
station_router = APIRouter()


@station_router.get(
    '/',
    response_model=List[StationDetailedView],
    status_code=status.HTTP_200_OK,
    description="Return a list of all installed stations.")
@handle_exceptions(logger)
async def get_all_stations(
    user: User = Depends(auth_check)
):
    """Return a list of all installed stations."""
    return await station_services.get_all_stations(user)


@station_router.get(
    '/discover',
    response_model=List[StationLocationView],
    status_code=status.HTTP_200_OK,
    description="Get a list of all stations within a range of a given location.")
@handle_exceptions(logger)
async def get_nearby_stations(
    lat: Annotated[float, Query(
        ge=0, le=180, example=49.0,
        description="Latitude in degrees."
    )],
    lon: Annotated[float, Query(
        ge=-180, le=180, example=49.0,
        description="Longitude in degrees."
    )],
    radius: Annotated[float, Query(
        ge=1, le=10000, example=1000,
        description="Radius in meters."
    )],
    amount: int = 100,
    user: User = Depends(auth_check)
) -> List[StationLocationView]:
    """Return a list of station withing a given range of a location."""
    return await station_services.discover(user, lat, lon, radius, amount)


@station_router.get(
    '/{callsign}/details',
    response_model=StationDetailedView,
    status_code=status.HTTP_200_OK,
    description='Get detailed information about a station.'
)
@handle_exceptions(logger)
async def get_station_details(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    user: User = Depends(auth_check)
) -> StationDetailedView:
    """Get detailed information about a station"""
    return await station_services.get_details(
        user=user,
        callsign=callsign)


@station_router.get(
    '/{callsign}/dashboard',
    response_model=StationDashboardView,
    status_code=status.HTTP_200_OK,
    description='Get the dashboard overview for this station.'
)
@handle_exceptions(logger)
async def get_dashboard_view(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    user: User = Depends(auth_check),
) -> int:
    """'Get the dashboard overview for this station.'"""
    return await station_services.get_dashboard_view(
        user=user,
        callsign=callsign
    )


@station_router.get(
    '/{callsign}/lockers',
    status_code=status.HTTP_200_OK,
    response_model=List[LockerView],
    description='Get a list of lockers at the station.'
)
@handle_exceptions(logger)
async def get_lockers(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    user: User = Depends(auth_check)
) -> List[LockerView]:
    """Get a list of lockers at the station"""
    return await station_services.get_lockers(
        user=user,
        callsign=callsign)


@station_router.get(
    '/{callsign}/locker_availability',
    response_model=List[LockerTypeAvailabilityView],
    status_code=status.HTTP_200_OK,
    description='Get the availability of lockers at the station.'
)
@handle_exceptions(logger)
async def get_locker_availabilities(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    user: User = Depends(auth_check)
) -> List[LockerTypeAvailabilityView]:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_overview(
        user=user,
        callsign=callsign)


@station_router.get(
    '/{callsign}/lockers/{station_index}',
    response_model=LockerAvailabilityView,
    status_code=status.HTTP_200_OK,
    description='Get information about a locker at the station'
)
@handle_exceptions(logger)
async def get_locker_by_index(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    station_index: Annotated[int, Path(
        gt=0, lt=100, example=8,
        description="Index of the locker in the station."
    )],
    user: User = Depends(auth_check)
) -> Optional[LockerAvailabilityView]:
    """Get information about a locker at the station"""
    return await station_services.get_locker_by_index(
        user=user,
        callsign=callsign,
        station_index=station_index)


@station_router.post(
    '/{callsign}/reservation',
    response_model=None,
    status_code=status.HTTP_202_ACCEPTED,
    description='Reserve a locker at the station.')
@handle_exceptions(logger)
async def reserve_locker_at_station(
    response: Response,
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    locker_type: Annotated[str, Query(enum=LOCKER_TYPE_NAMES)],
    user: User = Depends(auth_check)
) -> StationDetailedView:
    """Reserve a station for a user"""
    try:  # TODO: Improve error handling here
        await station_services.handle_reservation_request(
            callsign=callsign,
            locker_type_name=locker_type,
            user=user,
            response=response)
    except LockerNotAvailableException as e:
        logger.warning(e)
        raise HTTPException(status_code=404, detail=e) from e


@station_router.delete(
    '/{callsign}/reserve_cancel',
    response_model=None,
    description='Cancel a station reservation.',
    status_code=status.HTTP_202_ACCEPTED)
@handle_exceptions(logger)
async def request_reservation_cancelation(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    user: User = Depends(auth_check)
):
    """Cancel a station reservation"""
    await station_services.handle_reservation_cancel_request(
        user=user,
        callsign=callsign,)


@station_router.put(
    '/{callsign}/reset_queue',
    response_model=StationDetailedView,
    description='Reset the queue at the station.',
    status_code=status.HTTP_202_ACCEPTED)
@handle_exceptions(logger)
async def reset_station_queue(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    user: User = Depends(auth_check)
) -> StationDetailedView:
    """Reset the queue at the station. This is helpful if the queue is stale."""
    return await station_services.reset_queue(user=user, callsign=callsign)


@station_router.get(
    '/{callsign}/state',
    response_model=StationDetailedView,
    description='Get the high-level station state which indicates general availability.',
    status_code=status.HTTP_200_OK)
@handle_exceptions(logger)
async def get_station_state(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    user: User = Depends(auth_check)
) -> StationDetailedView:
    """Get the high-level station state which indicates general availability."""
    return await station_services.get_station_state(
        user=user,
        callsign=callsign)


@station_router.patch(
    '/{callsign}/state',
    response_model=StationDetailedView,
    description='Set the high-level station state which indicates general availability',
    status_code=status.HTTP_202_ACCEPTED)
@handle_exceptions(logger)
async def set_station_state(
        callsign: Annotated[str, Path(
            pattern='^[A-Z]{6}$', example="MUCODE",
            description="Unique identifier of the station.")],
    state: StationState,
    user: User = Depends(auth_check)
):
    """Set the high-level station state which indicates general availability."""
    return await station_services.set_station_state(
        user=user,
        callsign=callsign,
        station_state=state)

# Set expected topics
TERMINAL_INST_TOPIC = 'stations/+/instruct'
TERMINAL_CONF_TOPIC = 'stations/+/confirm'
TERMINAL_REP_TOPIC = 'stations/+/report'
LOCKER_INST_TOPIC = 'lockers/+/instruct'
LOCKER_CONF_TOPIC = 'lockers/+/confirm'
LOCKER_REP_TOPIC = 'lockers/+/report'


@validate_mqtt_topic(TERMINAL_CONF_TOPIC, [ObjId])
@fast_mqtt.subscribe(TERMINAL_CONF_TOPIC)
@handle_exceptions(logger)
async def handle_terminal_confirmation(
        _client, topic, payload, _qos, _properties):
    """Handle a confirmation from a station that it entered a mode at its terminal"""
    callsign = topic.split('/')[1]
    mode = payload.decode('utf-8').upper()

    if not mode:
        logger.warning(
            f"Invalid station terminal report from station {callsign}.")
        return

    # Check if the mode is a valid TerminalState
    if mode in TerminalState.__members__:
        await station_services.handle_terminal_state_confirmation(
            callsign, TerminalState[mode])


@validate_mqtt_topic(TERMINAL_REP_TOPIC, [ObjId])
@fast_mqtt.subscribe(TERMINAL_REP_TOPIC)
@handle_exceptions(logger)
async def handle_terminal_report(
        _client, topic, payload, _qos, _properties):
    """Handle a report from a station terminal"""
    callsign = topic.split('/')[1]
    action_type = payload.decode('utf-8')

    action_state = (SessionState.VERIFICATION if action_type.lower() ==
                    'verification' else SessionState.PAYMENT)
    terminal_state = (TerminalState.VERIFICATION if action_type.lower() ==
                      'verification' else TerminalState.PAYMENT)

    logger.info(
        f"Station '{callsign}' reported {action_type.upper()}.")

    await station_services.handle_terminal_report(
        callsign=callsign,
        expected_session_state=action_state,
        expected_terminal_state=terminal_state,
    )


@validate_mqtt_topic(LOCKER_CONF_TOPIC, [str])
@fast_mqtt.subscribe(LOCKER_CONF_TOPIC)
@handle_exceptions(logger)
async def handle_locker_confirmation(
        _client: Any, topic: str, payload: bytes, _qos: int, _properties: Any):
    """Handle a locker confirmation from a station"""
    topic_parts = topic.split('/')
    locker_callsign: str = topic_parts[1]
    confirmation: str = payload.decode('utf-8').lower()

    if confirmation != LockerState.UNLOCKED.value:
        raise InvalidLockerReportException(
            callsign=locker_callsign,
            raise_http=False)

    await locker_services.handle_unlock_confirmation(locker_callsign)


@validate_mqtt_topic(LOCKER_REP_TOPIC, [str])
@fast_mqtt.subscribe(LOCKER_REP_TOPIC)
@handle_exceptions(logger)
async def handle_locker_report(
        _client: Any, topic: str, payload: bytes, _qos: int, _properties: Any):
    """Handle a locker report from a station"""
    # Import station and locker information
    topic_parts = topic.split('/')
    locker_callsign: str = topic_parts[1]
    report: str = payload.decode('utf-8').lower()

    if report != LockerState.LOCKED.value:
        raise InvalidLockerReportException(
            callsign=locker_callsign,
            raise_http=False)

    try:
        await locker_services.handle_lock_report(
            locker_callsign)
    except InvalidLockerReportException as e:
        logger.error(e)
