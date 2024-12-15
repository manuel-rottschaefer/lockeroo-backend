"""Provides utility functions for the station management backend."""

# Basics
from typing import Dict, List, Optional

import yaml
# Beanie
from beanie.operators import In, Near, Set
# API services
from fastapi import Response, status

# Entities
from src.entities.station_entity import Station
from src.entities.locker_entity import Locker
from src.entities.session_entity import Session
from src.entities.task_entity import Task, restart_expiration_manager
# Models
from src.exceptions.station_exceptions import (
    InvalidStationReportException,
    InvalidTerminalStateException,
    StationNotFoundException)
from src.models.locker_models import LockerModel
from src.models.session_models import SessionModel, SessionStates, ACTIVE_SESSION_STATES
from src.models.station_models import (StationLockerAvailabilities,
                                       StationModel, StationStates,
                                       StationType, StationView,
                                       TerminalStates)
from src.models.task_models import TaskItemModel, TaskTypes, TaskStates
# Services
from src.services.logging_services import logger
from src.exceptions.task_exceptions import TaskNotFoundException
from src.exceptions.session_exceptions import (
    InvalidSessionStateException)
from src.exceptions.locker_exceptions import LockerNotFoundException

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


async def get_details(callsign: str, response: Response) -> Optional[StationView]:
    """Get detailed information about a station."""
    # Get station data from the database
    station: Station = await Station().find(callsign=callsign)
    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=callsign)
    return station.document


async def get_active_session_count(callsign: str, response: Response) -> Optional[int]:
    """Get the amount of currently active sessions at this station."""
    station: Station = await Station().find(callsign=callsign)
    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=callsign)

    return await SessionModel.find(
        SessionModel.assigned_station == station.id,
        In(SessionModel.session_state,
           ACTIVE_SESSION_STATES),  # pylint: disable=no-member
        fetch_links=True
    ).count()


async def get_locker_by_index(
        callsign: str, locker_index: int, response: Response,) -> Optional[LockerModel]:
    """Get the locker at a station by its index."""
    # 1: Get the station
    station: Station = await Station().find(callsign=callsign)
    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=callsign)

    # 2: Get the assigned locker
    locker: Locker = await Locker().find(
        station=station.document.id, index=locker_index)
    if not locker.exists:
        raise LockerNotFoundException(locker_id=None)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        # TODO: Raise logger error here
    return locker.document


async def get_locker_overview(
        callsign: str, response: Response, ) -> Optional[StationLockerAvailabilities]:
    """Determine for each locker type if it is available at the given station."""

    # 1: Check whether the station exists
    station: Station = await Station().find(callsign=callsign)

    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=callsign)

    # 2: Create a list of locker availabilities
    # TODO: Rework this part with dynamic locker types
    availability = StationLockerAvailabilities()
    locker_types = ['small', 'medium', 'large']
    for locker_type in locker_types:
        locker_data = await LockerModel.find(
            LockerModel.station == callsign.callsign,
            LockerModel.lockerType.name == locker_type,
            # LockerModel.state == LockerStates.operational,
        ).to_list()

        availability[locker_type] = len(locker_data) != 0

    return availability


async def set_station_state(callsign: str, station_state: StationStates) -> StationView:
    """Set the state of a station."""
    station: Station = Station().find(callsign=callsign)
    await station.register_station_state(station_state)
    return station.document


async def reset_queue(callsign: str, response: Response) -> StationView:
    """Reset the queue of the station by putting all queue
    items in state QUEUED and re-evaluating the queue."""
    # 1: Find the assigned station
    station: Station = await Station().find(callsign=callsign)
    if not station.exists():
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=callsign)

    # 2: Get all stale queue items at the station
    tasks: List[TaskItemModel] = await TaskItemModel.find(
        TaskItemModel.assigned_station.id == station.document.id,  # pylint: disable=no-member
        TaskItemModel.task_state == TaskStates.PENDING
    ).sort((TaskItemModel.created_ts)).first_or_none()

    # 3: Set all to state QUEUED
    await tasks.update(Set({TaskItemModel.task_state: TaskStates.QUEUED}))

    # 4: Re-evaluate the queue
    first_task: Task = Task(tasks[0])
    await first_task.activate()


async def handle_terminal_report(
        callsign: str,
        expected_session_state: SessionStates,
        expected_terminal_state: TerminalStates
) -> None:
    """This handler processes reports of completed actions at a station.
        It verifies the authenticity of the report and then updates the state
        values for the station and the assigned session as well as notifies
        the client so that the user can proceed. """

    # 1: Find the assigned station
    station: Station = await Station().find(callsign=callsign)
    if not station.exists:
        raise StationNotFoundException(
            callsign=callsign, raise_http=False)

    # 2: Find the assigned task
    task: Task = await Task().find(
        task_type=TaskTypes.TERMINAL,
        task_state=TaskStates.PENDING,
        queued_state=expected_session_state,
        assigned_station=station.document.id,
    )
    if not task.exists:
        raise TaskNotFoundException(
            assigned_station=callsign,
            task_type=TaskTypes.USER,
            raise_http=False)
    await task.fetch_link(TaskItemModel.assigned_session)

    # 2: Get the assigned session
    assert (task.assigned_session is not None
            ), f"Task '{task.id}' exists but has no assigned session."
    session = Session(task.assigned_session)

    if session.session_state != expected_session_state:
        raise InvalidSessionStateException(
            session_id=session.id,
            expected_states=[expected_session_state],
            actual_state=session.session_state,
            raise_http=False)

    # 3: Check whether the station is currently told to await an action
    station: Station = Station(session.assigned_station)
    if station.terminal_state != expected_terminal_state:
        raise InvalidTerminalStateException(
            station_callsign=callsign,
            expected_state=expected_terminal_state,
            actual_state=station.terminal_state,
            raise_http=False)

    # 4: Find the locker that belongs to this session
    locker: Locker = Locker(session.assigned_locker)

    # 5: Update terminal, locker and task states
    await station.register_terminal_state(TerminalStates.IDLE)
    await task.complete()

    # 6: Restart the task manager
    await restart_expiration_manager()

    # 7: Await station to confirm locker state
    await Task().create(
        task_type=TaskTypes.CONFIRMATION,
        locker=locker.document,
        session=session.document,
        queued_state=None,
        timeout_states=[SessionStates.ABORTED],
        has_queue=False
    )


async def handle_terminal_confirmation(
        callsign: str, terminal_state: TerminalStates):
    """Process a station report about its terminal state."""
    logger.info(f"Station '{callsign}' confirmed terminal in {
                terminal_state}.")
    # 1: Find the assigned station
    station: Station = await Station().find(callsign=callsign)
    if not station.exists:
        raise StationNotFoundException(
            callsign=callsign, raise_http=False)

    # 2: If the terminal state matches the current state, ignore the report
    if station.terminal_state == terminal_state:
        return

    # 3: Find assigned task
    task: Task = await Task().find(
        task_type=TaskTypes.CONFIRMATION,
        task_state=TaskStates.PENDING,
        assigned_station=station.document.id)
    if not task.exists:
        raise InvalidStationReportException(
            callsign, terminal_state.value,
            raise_http=False)
    await task.fetch_link(TaskItemModel.assigned_session)

    # 4: Find assigned session and set to queued state
    session: Session = Session(task.assigned_session)

    # 5: Update the terminal state
    await station.register_terminal_state(terminal_state)

    # 6: Complete previous task
    await task.complete()
    await restart_expiration_manager()

    # 7: Launch the new user task
    await session.document.sync()
    await Task().create(
        task_type=TaskTypes.TERMINAL,
        station=station.document,
        session=session.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.PAYMENT_SELECTED,
                        SessionStates.EXPIRED],
        has_queue=False
    )
