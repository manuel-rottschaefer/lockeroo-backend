"""Provides utility functions for the station management backend."""

# Basics
from typing import Dict, List, Optional

import yaml
from beanie import PydanticObjectId as ObjId
# Beanie
from beanie.operators import Near, Set
# API services
from fastapi import Response, status

from src.entities.locker_entity import Locker
from src.entities.session_entity import Session
# Entities
from src.entities.station_entity import Station
from src.entities.task_entity import Task
# Models
from src.models.locker_models import LockerModel, LockerStates
from src.models.session_models import SessionModel, SessionStates
from src.models.station_models import (StationLockerAvailabilities,
                                       StationModel, StationStates,
                                       StationType, StationView,
                                       TerminalStates)
from src.models.task_models import TaskItemModel, TaskStates, TaskTypes
# Services
from src.services.exception_services import ServiceExceptions
from src.services.logging_services import logger
from src.services.session_services import InvalidSessionStateException

# Singleton for pricing models
STATION_TYPES: Dict[str, StationType] = None

CONFIG_PATH = 'src/config/station_types.yml'

if STATION_TYPES is None:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as cfg:
            type_dicts = yaml.safe_load(cfg)
            STATION_TYPES = {name: StationType(name=name, **details)
                             for name, details in type_dicts.items()}
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {CONFIG_PATH}.")
        STATION_TYPES = {}
    except yaml.YAMLError as e:
        logger.warning(f"Error parsing YAML configuration: {e}")
        STATION_TYPES = {}
    except TypeError as e:
        logger.warning(f"Data structure mismatch: {e}")
        STATION_TYPES = {}


async def discover(lat: float, lon: float, radius: int,
                   amount: int) -> List[StationView]:
    """Return a list of stations within a given range around a location"""
    stations: List[StationView] = await StationModel.find(
        Near(StationModel.location, lat, lon, max_distance=radius)
    ).limit(amount).to_list()
    return stations


class StationNotFoundException(Exception):
    """Exception raised when a station cannot be found by a given query."""
    # TODO: We may not need this as this is a user error

    def __init__(self, callsign: str = None, station_id: ObjId = None):
        super().__init__()
        self.station = callsign if callsign else station_id
        logger.warning(
            f"Could not find station '{self.station}' in database.")

    def __str__(self):
        return f"Station '{self.station}' not found.)"


class InvalidStationReportException(Exception):
    """Exception raised when a station reports an action that is not expected by the backend."""

    def __init__(self, station_callsign: str, reported_state: str):
        super().__init__()
        self.station_callsign = station_callsign
        logger.warning(
            f"Received non-expected report of {reported_state} at '{station_callsign}'.")

    def __str__(self):
        return f"Invalid station report at station '{self.station_callsign}'.)"


class InvalidTerminalStateException(Exception):
    """Exception raised when a station reports a terminal mode that is not expected by the backend."""

    def __init__(self,
                 station_callsign: str,
                 expected_state: TerminalStates,
                 actual_state: TerminalStates):
        super().__init__()
        self.station_callsign = station_callsign
        self.expected_state = expected_state
        self.actual_state = actual_state
        logger.warning(
            f"Locker at station '{station_callsign}' should be in {expected_state}, but has been reported as {actual_state}.")

    def __str__(self):
        return f"Invalid station report at station '{self.station_callsign}'.)"


async def get_details(call_sign: str, response: Response) -> Optional[StationView]:
    """Get detailed information about a station."""
    # Get station data from the database
    station: Station = await Station().find(call_sign=call_sign)
    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=call_sign)
    return station.document


async def get_active_session_count(call_sign: str, response: Response) -> Optional[int]:
    """Get the amount of currently active sessions at this station."""
    station: Station = await Station().find(call_sign=call_sign)
    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=call_sign)

    return await SessionModel.find(
        SessionModel.assigned_station == station.id,
        SessionModel.session_state.is_active is True,  # pylint: disable=no-member
        fetch_links=True
    ).count()


async def get_locker_by_index(
        call_sign: str, locker_index: int, response: Response,) -> Optional[LockerModel]:
    """Get the locker at a station by its index."""
    # 1: Get the assigned locker
    locker: Locker = await Locker().fetch(call_sign=call_sign, index=locker_index)
    if not locker.exists:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        # TODO: Raise logger error here
    return locker.document


async def get_locker_overview(call_sign: str, response: Response, ) -> Optional[StationLockerAvailabilities]:
    """Determine for each locker type if it is available at the given station."""

    # 1: Check whether the station exists
    station: Station = await Station().find(call_sign=call_sign)

    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=call_sign)

    # 2: Create a list of locker availabilities
    # TODO: Rework this part with dynamic locker types
    availability = StationLockerAvailabilities()
    locker_types = ['small', 'medium', 'large']
    for locker_type in locker_types:
        locker_data = await LockerModel.find(
            LockerModel.station == call_sign.call_sign,
            LockerModel.lockerType.name == locker_type,
            # LockerModel.state == LockerStates.operational,
        ).to_list()

        availability[locker_type] = len(locker_data) != 0

    return availability


async def set_station_state(call_sign: str, station_state: StationStates) -> StationView:
    """Set the state of a station."""
    station: Station = Station().find(call_sign=call_sign)
    await station.register_station_state(station_state)
    return station.document


async def reset_queue(call_sign: str, response: Response) -> StationView:
    """Reset the queue of the station by putting all queue
    items in state QUEUED and re-evaluating the queue."""
    # 1: Find the assigned station
    station: Station = await Station().find(call_sign=call_sign)
    if not station.exists():
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=call_sign)

    # 2: Get all stale queue items at the station
    tasks: List[TaskItemModel] = await TaskItemModel.find(
        TaskItemModel.assigned_station == station.id,
        TaskItemModel.task_state == TaskStates.PENDING
    ).sort(TaskItemModel.created_ts)

    # 3: Set all to state QUEUED
    await tasks.update(Set({TaskItemModel.task_state: TaskStates.QUEUED}))

    # 4: Re-evaluate the queue
    first_task: Task = Task(tasks[0])
    await first_task.activate()


async def handle_action_report(
        call_sign: str,
        expected_session_state: SessionStates,
        expected_terminal_state: TerminalStates
) -> None:
    """This handler processes reports of completed actions at a station.
        It verifies the authenticity of the report and then updates the state
        values for the station and the assigned session as well as notifies
        the client so that the user can proceed. """
    # 1: Find the assigned task
    task: Task = await Task().find(
        call_sign=call_sign,
        task_type=TaskTypes.USER,
        task_state=TaskStates.PENDING)
    if not task.exists():
        raise InvalidStationReportException(
            call_sign, expected_terminal_state.value,)
    await task.fetch_links()

    # 2: Get the assigned session
    assert task.assigned_session is not None, f"Task '{
        task.id}' exists but has no assigned session."
    session = Session(task.assigned_session)
    await session.fetch_links()

    if task.assigned_session.session_state != expected_session_state:
        raise InvalidSessionStateException(
            session.id, expected_session_state, session.session_state)

    # 3: Check whether the station is currently told to await an action
    station: Station = Station(session.assigned_station)
    if station.terminal_state != expected_terminal_state:
        logger.info(ServiceExceptions.INVALID_TERMINAL_STATE,
                    station=call_sign, detail=station.terminal_state)
        return

    # 4: Find the locker that belongs to this session
    locker: Locker = Locker(session.assigned_locker)

    # 5: Update terminal, locker and task states
    await station.register_terminal_state(TerminalStates.IDLE)
    await locker.set_state(LockerStates.UNLOCKED)
    await task.set_state(TaskStates.COMPLETED)

    # 6: Restart the task manager
    await restart_expiration_manager()

    # 7: Await station to confirm locker state
    await Task().create(
        task_type=TaskTypes.LOCKER,
        station=station.document,
        session=session.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.ABORTED],
        has_queue=False
    )


async def handle_terminal_confirmation(call_sign: str, terminal_state: TerminalStates):
    """Process a station report about its terminal state."""
    # 1: Find the assigned station
    station: Station = await Station().find(call_sign=call_sign)
    await station.register_terminal_state(terminal_state)

    # 2: Find assigned task
    task: Task = await Task().find(
        call_sign=call_sign,
        task_type=TaskTypes.TERMINAL,
        task_state=TaskStates.PENDING)
    await task.fetch_links()

    # 3: Find assigned session and set to queued state
    session: Session = Session(task.assigned_session)

    # 2: Complete previous task
    await task.set_state(TaskStates.COMPLETED)
    await restart_expiration_manager()

    # 3: Launch the new user task
    await Task().create(
        task_type=TaskTypes.USER,
        station=station.document,
        session=session.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.PAYMENT_SELECTED,
                        SessionStates.EXPIRED],
        has_queue=False
    )
