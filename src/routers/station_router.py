"""
This module contains the station router which handles all station related requests
"""
# Basics
from typing import Annotated, Any, List, Optional
from uuid import uuid4
# FastAPI & Beanie
from beanie import PydanticObjectId as ObjId
from fastapi import APIRouter, Path, Header, Depends, Query, status
# Exceptions
from src.exceptions.locker_exceptions import InvalidLockerReportException
from src.models.locker_models import (
    LockerState,
    LockerTypeAvailabilityView,
    LockerView)
# Entities
from src.entities.user_entity import User
# Models
from src.models.station_models import StationState, StationView, TerminalState
from src.models.session_models import SessionState
from src.models.locker_models import LOCKER_TYPE_NAMES
# Services
from src.services import station_services, locker_services
from src.services.exception_services import handle_exceptions
from src.services.logging_services import logger_service as logger
from src.services.mqtt_services import fast_mqtt, validate_mqtt_topic
from src.services.auth_services import require_auth

# Create the router
station_router = APIRouter()


@station_router.get(
    '/',
    response_model=List[StationView],
    status_code=status.HTTP_200_OK,
    description="Return a list of all installed stations.")
@ handle_exceptions(logger)
async def get_all_stations():
    """Return a list of all installed stations."""
    return await station_services.get_all_stations()


@station_router.get(
    '/discover',
    response_model=List[StationView],
    status_code=status.HTTP_200_OK,
    description="Get a list of all stations within a range of a given location.")
@ handle_exceptions(logger)
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
        amount: int = 100) -> List[StationView]:
    """Return a list of station withing a given range of a location."""
    return await station_services.discover(lat, lon, radius, amount)


@station_router.get(
    '/{callsign}/details',
    response_model=StationView,
    status_code=status.HTTP_200_OK,
    description='Get detailed information about a station.'
)
@ handle_exceptions(logger)
async def get_station_details(
        callsign: Annotated[str, Path(
            pattern='^[A-Z]{6}$', example="MUCODE",
            description="Unique identifier of the station.")],
) -> StationView:
    """Get detailed information about a station"""
    return await station_services.get_details(
        callsign=callsign)


@station_router.get(
    '/{callsign}/active_session_count',
    response_model=int,
    status_code=status.HTTP_200_OK,
    description='Get the amount of currently active sessions at this station.'
)
@ handle_exceptions(logger)
async def get_active_session_count(
        callsign: Annotated[str, Path(
            pattern='^[A-Z]{6}$', example="MUCODE",
            description="Unique identifier of the station.")],
) -> int:
    """Get the amount of currently active sessions at this station."""
    return await station_services.get_active_session_count(
        callsign=callsign)


@station_router.get(
    '/{callsign}/lockers',
    response_model=List[LockerTypeAvailabilityView],
    status_code=status.HTTP_200_OK,)
@ handle_exceptions(logger)
async def get_locker_overview(
        callsign: Annotated[str, Path(
            pattern='^[A-Z]{6}$', example="MUCODE",
            description="Unique identifier of the station.")],
) -> List[LockerTypeAvailabilityView]:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_overview(
        callsign=callsign)


@station_router.get(
    '/{callsign}/lockers/{station_index}',
    response_model=LockerView,
    status_code=status.HTTP_200_OK,
)
@ handle_exceptions(logger)
async def get_locker_by_index(
        callsign: Annotated[str, Path(
            pattern='^[A-Z]{6}$', example="MUCODE",
            description="Unique identifier of the station.")],
        station_index: Annotated[int, Path(
            gt=0, lt=100, example=8,
            description="Index of the locker in the station."
        )],
) -> Optional[LockerView]:
    """Get the availability of lockers at the station"""
    return await station_services.get_locker_by_index(
        callsign=callsign,
        station_index=station_index,
    )

# TODO: Own reservation router


@station_router.post(
    '/{callsign}/reservation',
    response_model=None,
    status_code=status.HTTP_202_ACCEPTED,
)
@ handle_exceptions(logger)
async def reserve_locker_at_station(
    callsign: str,
    # callsign: Annotated[str, Path(
    #    pattern='^[A-Z]{6}$', example="MUCODE",
    #    description="Unique identifier of the station.")],
    locker_type: Annotated[str, Query(enum=LOCKER_TYPE_NAMES)],
    _user: Annotated[str, Header(
        alias="user", example=uuid4(),
        description="User UUID (only for debug)")],
    access_info: User = Depends(require_auth),
) -> StationView:
    """Reserve a station for a user"""
    await station_services.handle_reservation_request(
        callsign=callsign,
        locker_type=locker_type,
        user=access_info)


@station_router.patch(
    '/{callsign}/reset_queue',
    response_model=StationView,
    status_code=status.HTTP_202_ACCEPTED,)
@ handle_exceptions(logger)
async def reset_station_queue(
        callsign: Annotated[str, Path(
            pattern='^[A-Z]{6}$', example="MUCODE",
            description="Unique identifier of the station.")],
) -> StationView:
    """Reset the queue at the station. This is helpful if the queue is stale."""
    return await station_services.reset_queue(callsign=callsign)


@station_router.put(
    '/{callsign}/state',
    response_model=StationView,
    status_code=status.HTTP_202_ACCEPTED,)
@ handle_exceptions(logger)
async def set_station_state(
        callsign: Annotated[str, Path(
            pattern='^[A-Z]{6}$', example="MUCODE",
            description="Unique identifier of the station.")],
        state: StationState) -> StationView:
    """Set the high-level station state which indicates general availability."""
    return await station_services.set_station_state(
        callsign=callsign,
        station_state=state)


@station_router.delete(
    '/{callsign}/reserve_cancel',
    response_model=None,
    status_code=status.HTTP_202_ACCEPTED,

)
@ handle_exceptions(logger)
async def request_reservation_cancelation(
    callsign: Annotated[str, Path(
        pattern='^[A-Z]{6}$', example="MUCODE",
        description="Unique identifier of the station.")],
    _user: Annotated[str, Header(
        alias="user", example=uuid4(),
        description="User UUID (only for debug)")],
        access_info: User = Depends(require_auth),
):
    """Cancel a station reservation"""
    await station_services.handle_reservation_cancel_request(
        callsign=callsign,
        user=access_info
    )


@validate_mqtt_topic('stations/+/terminal/confirm', [ObjId])
@fast_mqtt.subscribe('stations/+/terminal/confirm')
async def handle_terminal_confirmation(
        _client, topic, payload, _qos, _properties) -> None:
    """Handle a confirmation from a station that it entered a mode at its terminal"""
    callsign = topic.split('/')[1]
    mode = payload.decode('utf-8').upper()
    terminal_state: TerminalState

    if not mode:
        logger.warning(
            f"Invalid station terminal report from station {callsign}.")
        return

    # if mode in terminalstates
    if mode in TerminalState.__members__:
        terminal_state = TerminalState[mode]
    else:
        return

    await station_services.handle_terminal_state_confirmation(
        callsign, terminal_state)


@validate_mqtt_topic('stations/+/verification/report', [ObjId])
@fast_mqtt.subscribe('stations/+/verification/report')
@ handle_exceptions(logger)
async def handle_verification_report(
        _client, topic, payload, _qos, _properties) -> None:
    """Handle a payment verification report from a station"""
    callsign = topic.split('/')[1]
    card_id = payload.decode('utf-8')

    logger.info(
        f"Station '{callsign}' reported {SessionState.VERIFICATION} with card '#{card_id}'.")

    await station_services.handle_terminal_report(
        callsign=callsign,
        expected_session_state=SessionState.VERIFICATION,
        expected_terminal_state=TerminalState.VERIFICATION,
    )


@validate_mqtt_topic('stations/+/payment/report', [ObjId])
@fast_mqtt.subscribe('stations/+/payment/report')
@ handle_exceptions(logger)
async def handle_station_payment_report(
        _client, topic, _payload, _qos, _properties) -> None:
    """Handle a payment report from a station"""
    callsign = topic.split('/')[1]

    logger.info(
        (f"Station '#{callsign}' reported {SessionState.PAYMENT} "
         f"with card '#123456'."))

    await station_services.handle_terminal_report(
        callsign=callsign,
        expected_session_state=SessionState.PAYMENT,
        expected_terminal_state=TerminalState.PAYMENT
    )


@validate_mqtt_topic('stations/+/locker/+/confirm', [ObjId, int])
@fast_mqtt.subscribe('stations/+/locker/+/confirm')
@ handle_exceptions(logger)
async def handle_locker_confirmation(
        _client: Any, topic: str, payload: bytes, _qos: int, _properties: Any) -> None:
    """Handle a locker confirmation from a station"""
    # Import station and locker information
    topic_parts = topic.split('/')
    callsign: str = topic_parts[1]
    station_index: int = int(topic_parts[3])
    confirmation: str = payload.decode('utf-8').lower()

    if confirmation != LockerState.UNLOCKED.value:
        raise InvalidLockerReportException(
            station_index=station_index,
            raise_http=False)

    await locker_services.handle_unlock_confirmation(callsign, station_index)


@validate_mqtt_topic('stations/+/locker/+/report', [ObjId, int])
@fast_mqtt.subscribe('stations/+/locker/+/report')
@ handle_exceptions(logger)
async def handle_locker_report(
        _client: Any, topic: str, payload: bytes, _qos: int, _properties: Any) -> None:
    """Handle a locker report from a station"""
    # Import station and locker information
    topic_parts = topic.split('/')
    callsign: str = topic_parts[1]
    station_index: int = int(topic_parts[3])
    report: str = payload.decode('utf-8').lower()

    if report != LockerState.LOCKED.value:
        raise InvalidLockerReportException(
            station_index=station_index,
            raise_http=False)

    try:
        await locker_services.handle_lock_report(
            callsign, station_index)
    except InvalidLockerReportException as e:
        logger.error(e)
