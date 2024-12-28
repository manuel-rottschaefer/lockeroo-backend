"""Provides utility functions for the station management backend."""

# Basics
from datetime import datetime
from typing import Dict, List, Optional

import yaml
# Beanie
from beanie import SortDirection
from beanie.operators import In, Near, Set
# API services
from fastapi import Response, status

from src.entities.locker_entity import Locker
from src.entities.session_entity import Session
# Entities
from src.entities.station_entity import Station
from src.entities.task_entity import Task
from src.exceptions.locker_exceptions import LockerNotFoundException
from src.exceptions.session_exceptions import InvalidSessionStateException
# Models
from src.exceptions.station_exceptions import (InvalidTerminalStateException,
                                               StationNotFoundException)
from src.exceptions.task_exceptions import TaskNotFoundException
from src.models.locker_models import (LOCKER_TYPES, LockerAvailability,
                                      LockerModel, LockerTypeAvailability)
from src.models.session_models import (ACTIVE_SESSION_STATES, SessionModel,
                                       SessionState)
from src.models.station_models import (StationModel, StationStates,
                                       StationType, StationView, TerminalState)
from src.models.task_models import (TaskItemModel, TaskState, TaskTarget,
                                    TaskType)
# Services
from src.services.logging_services import logger

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


async def get_all_stations() -> List[StationView]:
    """Returns a list of all installed stations."""
    return await StationModel.find(
        StationModel.installed_at < datetime.now()
    ).limit(100)


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
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none()
    )
    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=callsign)
    return station.doc


async def get_active_session_count(callsign: str, response: Response) -> Optional[int]:
    """Get the amount of currently active sessions at this station."""
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none()
    )
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
        callsign: str, station_index: int, response: Response,) -> Optional[LockerModel]:
    """Get the locker at a station by its index."""
    # 1: Get the station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none()
    )
    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=callsign)

    # 2: Get the assigned locker
    locker: Locker = Locker(await LockerModel.find(
        LockerModel.station == station.doc.id,
        LockerModel.station_index == station_index
    ).first_or_none())
    if not locker.exists:
        raise LockerNotFoundException(
            station=callsign,
            station_index=station_index)
    return locker.doc


async def get_locker_overview(
        callsign: str, response: Response, ) -> List[LockerTypeAvailability]:
    """Determine for each locker type if it is available at the given station."""
    # 1: Check whether the station exists
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none()
    )
    if not station.exists:
        response.status_code = status.HTTP_404_NOT_FOUND
        raise StationNotFoundException(callsign=callsign)

    # 2: Create a list of locker availabilities
    locker_type_availabilities: List[LockerTypeAvailability] = []
    for locker_type in LOCKER_TYPES:
        type_available_count = await LockerModel.find(
            LockerModel.station.callsign == callsign,  # pylint: disable=no-member
            LockerModel.locker_type.name == locker_type.name,  # pylint: disable=no-member
            LockerModel.availability == LockerAvailability.OPERATIONAL,
            fetch_links=True
        ).count()

        locker_type_availabilities.append(
            LockerTypeAvailability(
                locker_type=locker_type.name,
                station=callsign,
                installed_count=type_available_count,
                is_available=type_available_count > 0
            )
        )
    return locker_type_availabilities


async def set_station_state(callsign: str, station_state: StationStates) -> StationView:
    """Set the state of a station."""
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none()
    )
    await station.register_station_state(station_state)
    return station.doc


async def reset_queue(callsign: str) -> StationView:
    """Reset the queue of the station by putting all queue
    items in state QUEUED and re-evaluating the queue."""
    # 1: Find the assigned station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none()
    )
    if not station.exists():
        raise StationNotFoundException(callsign=callsign, raise_http=True)

    # 2: Get all stale queue items at the station
    tasks: List[TaskItemModel] = await TaskItemModel.find(
        TaskItemModel.assigned_station.id == station.doc.id,  # pylint: disable=no-member
        TaskItemModel.task_state == TaskState.PENDING
    ).sort((TaskItemModel.created_at, SortDirection.ASCENDING)).first_or_none()

    # 3: Set all to state QUEUED
    await tasks.update(Set({TaskItemModel.task_state: TaskState.QUEUED}))

    # 4: Re-evaluate the queue
    first_task: Task = Task(tasks[0])
    await first_task.activate()


async def handle_terminal_report(
        callsign: str,
        expected_session_state: SessionState,
        expected_terminal_state: TerminalState
) -> None:
    """This handler processes reports of completed actions at a station.
        It verifies the authenticity of the report and then updates the state
        values for the station and the assigned session as well as notifies
        the client so that the user can proceed. """
    # 1: Find the assigned task
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.TERMINAL,
        TaskItemModel.task_type == TaskType.REPORT,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_station.callsign == callsign,  # pylint: disable=no-member
        TaskItemModel.assigned_locker == None,  # pylint: disable=no-member singleton-comparison
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        raise TaskNotFoundException(
            assigned_station=callsign,
            task_type=TaskType.REPORT,
            raise_http=False)

    # 2: Find the assigned station
    station: Station = Station(task.doc.assigned_station)
    if not station.exists:
        raise StationNotFoundException(
            callsign=callsign, raise_http=False)

    # 3: Get the assigned session
    assert (task.assigned_session is not None
            ), f"Task '#{task.id}' exists but has no assigned session."
    session = Session(task.assigned_session)

    # 4: Check whether the station is currently told to await an action
    await station.doc.sync()
    if station.terminal_state != expected_terminal_state:
        raise InvalidTerminalStateException(
            station_callsign=callsign,
            expected_states=[expected_terminal_state],
            actual_state=station.terminal_state,
            raise_http=False)

    # 5: Check whether the session is currently in the expected state
    if session.session_state != expected_session_state:
        raise InvalidSessionStateException(
            session_id=session.id,
            expected_states=[expected_session_state],
            actual_state=session.session_state,
            raise_http=False)

    # 6: Await terminal to confirm idle
    await Task(await TaskItemModel(
        target=TaskTarget.TERMINAL,
        task_type=TaskType.CONFIRMATION,
        assigned_station=station.doc,
        assigned_session=session.doc,
        timeout_states=[SessionState.ABORTED],
        moves_session=False,
    ).insert()).activate()

    # 7: Update the session state
    # This must come after the task creation, otherwise the new task will not be started
    await task.complete()


async def handle_terminal_state_confirmation(
        callsign: str, confirmed_state: TerminalState):
    """Process a station report about its terminal state."""
    logger.info(f"Station '{callsign}' confirmed terminal in {
                confirmed_state}.")

    # 1: Find the affected station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none())
    await station.doc.sync()
    if not station.exists:
        raise StationNotFoundException(
            callsign=callsign, raise_http=False)
    if station.terminal_state == confirmed_state:
        raise InvalidTerminalStateException(
            station_callsign=callsign,
            expected_states=[
                state for state in TerminalState if state != confirmed_state],
            actual_state=confirmed_state)

    # Register the new state
    await station.register_terminal_state(confirmed_state)

    # 2: Find the pending task for this station
    # TODO: FIXME This query may retrieve wrong tasks
    pending_task: Task = Task(await TaskItemModel.find(
        TaskItemModel.assigned_station.id == station.id,  # pylint: disable=no-member
        TaskItemModel.target == TaskTarget.TERMINAL,
        TaskItemModel.task_type == TaskType.CONFIRMATION,
        TaskItemModel.task_state == TaskState.PENDING
    ).sort((
        TaskItemModel.created_at, SortDirection.DESCENDING
    )).first_or_none())
    if not pending_task.exists:
        raise TaskNotFoundException(
            assigned_station=callsign,
            task_type=TaskType.CONFIRMATION,
            raise_http=False)

    # 5: Get the assigned session
    await pending_task.doc.fetch_link(TaskItemModel.assigned_session)
    session: Session = Session(pending_task.doc.assigned_session)

    if confirmed_state == TerminalState.IDLE:
        next_task: Task = await Task.from_next_queued(station_id=station.id)
        if next_task.exists:
            await next_task.activate()

    # 6: Complete previous task
    await pending_task.complete()

    # 7: Create next task according to the session context
    if confirmed_state == TerminalState.VERIFICATION:
        await Task(await TaskItemModel(
            target=TaskTarget.TERMINAL,
            task_type=TaskType.REPORT,
            assigned_station=station.doc,
            assigned_session=session.doc,
            timeout_states=([SessionState.EXPIRED] if session.timeout_count >= 1
                            else [SessionState.PAYMENT_SELECTED, SessionState.EXPIRED]),
            moves_session=True,
        ).insert()).activate()

    elif confirmed_state == TerminalState.PAYMENT:
        await Task(await TaskItemModel(
            target=TaskTarget.TERMINAL,
            task_type=TaskType.REPORT,
            assigned_station=station.doc,
            assigned_session=session.doc,
            timeout_states=([SessionState.EXPIRED] if session.timeout_count >= 1
                            else [session.doc.session_state, SessionState.EXPIRED]),
            moves_session=True,
        ).insert()).activate()

    elif confirmed_state == TerminalState.IDLE:
        if pending_task.doc.from_expired:
            await Task(await TaskItemModel(
                target=TaskTarget.USER,
                task_type=TaskType.REPORT,
                assigned_station=station.doc,
                assigned_session=session.doc,
                timeout_states=[SessionState.EXPIRED],
                moves_session=False,
            ).insert()).activate()
        else:
            await Task(await TaskItemModel(
                target=TaskTarget.LOCKER,
                task_type=TaskType.CONFIRMATION,
                assigned_station=station.doc,
                assigned_session=session.doc,
                assigned_locker=session.assigned_locker,
                timeout_states=[SessionState.ABORTED],
                moves_session=False,
            ).insert()).activate()

    else:
        raise InvalidTerminalStateException(
            station_callsign=callsign,
            expected_states=[confirmed_state],
            actual_state=confirmed_state
        )
