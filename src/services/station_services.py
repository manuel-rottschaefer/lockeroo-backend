"""Provides utility functions for the station management backend."""

# Basics
from typing import Dict, List, Optional
import yaml
# Beanie
from beanie import SortDirection
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
    InvalidTerminalStateException,
    StationNotFoundException)
from src.models.locker_models import LockerModel
from src.models.session_models import SessionModel, SessionState, ACTIVE_SESSION_STATES
from src.models.station_models import (StationLockerAvailabilities,
                                       StationModel, StationStates,
                                       StationType, StationView,
                                       TerminalState)
from src.models.task_models import (
    TaskItemModel, TaskState, TaskType, TaskTarget
)
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
        callsign: str, locker_index: int, response: Response,) -> Optional[LockerModel]:
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
        LockerModel.station_index == locker_index
    ).first_or_none())
    if not locker.exists:
        raise LockerNotFoundException(
            station=callsign,
            locker_index=locker_index)
    return locker.doc


async def get_locker_overview(
        callsign: str, response: Response, ) -> Optional[StationLockerAvailabilities]:
    """Determine for each locker type if it is available at the given station."""

    # 1: Check whether the station exists
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none()
    )

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
            expected_state=expected_terminal_state,
            actual_state=station.terminal_state,
            raise_http=False)

    # 5: Check whether the session is currently in the expected state
    if session.session_state != expected_session_state:
        raise InvalidSessionStateException(
            session_id=session.id,
            expected_states=[expected_session_state],
            actual_state=session.session_state,
            raise_http=False)

    # 6: Update the session state
    await task.complete()
    await restart_expiration_manager()

    # 7: Await terminal to confirm idle
    await Task(await TaskItemModel(
        target=TaskTarget.TERMINAL,
        task_type=TaskType.CONFIRMATION,
        assigned_station=station.doc,
        assigned_session=session.doc,
        timeout_states=[SessionState.ABORTED],
        moves_session=False,
    ).insert()).move_in_queue()


async def handle_terminal_state_confirmation(
        callsign: str, confirmed_state: TerminalState):
    """Process a station report about its terminal state."""
    logger.info(f"Station '{callsign}' confirmed terminal in {
                confirmed_state}.")

    # 1: Find the affected station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none())
    if not station.exists:
        raise StationNotFoundException(
            callsign=callsign, raise_http=False)
    if station.terminal_state == confirmed_state:
        logger.warning(
            "Invalid station report.")

    # Register the new state
    await station.register_terminal_state(confirmed_state)

    # 2: Find the pending task for this station
    # TODO: This may be unsafe
    pending_task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.TERMINAL,
        TaskItemModel.task_type == TaskType.CONFIRMATION,
        # TaskItemModel.task_state == TaskState.PENDING,
        In(TaskItemModel.task_state, [TaskState.QUEUED, TaskState.PENDING]),
        TaskItemModel.assigned_station.id == station.id  # pylint: disable=no-member
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

    # TODO: Experimental
    if confirmed_state == TerminalState.IDLE:
        next_task: Task = await Task.get_next_in_queue(station_id=station.id)
        if next_task.exists:
            await next_task.activate()

    # 6: Create next task according to the session context
    if confirmed_state == TerminalState.VERIFICATION:
        new_task: Task = Task(await TaskItemModel(
            target=TaskTarget.TERMINAL,
            task_type=TaskType.REPORT,
            assigned_station=station.doc,
            assigned_session=session.doc,
            timeout_states=[SessionState.PAYMENT_SELECTED,
                            SessionState.EXPIRED],
            moves_session=True,
        ).insert())

    elif confirmed_state == TerminalState.PAYMENT:
        new_task: Task = Task(await TaskItemModel(
            target=TaskTarget.TERMINAL,
            task_type=TaskType.REPORT,
            assigned_station=station.doc,
            assigned_session=session.doc,
            timeout_states=[session.doc.session_state,
                            SessionState.EXPIRED],
            moves_session=True,
        ).insert())

    elif confirmed_state == TerminalState.IDLE:
        new_task: Task = Task(await TaskItemModel(
            target=TaskTarget.LOCKER,
            task_type=TaskType.CONFIRMATION,
            assigned_station=station.doc,
            assigned_session=session.doc,
            assigned_locker=session.assigned_locker,
            timeout_states=[SessionState.ABORTED],
            moves_session=False,
        ).insert())

    else:
        raise InvalidTerminalStateException(
            station_callsign=callsign,
            expected_state=confirmed_state,
            actual_state=confirmed_state
        )

    # 7: Complete previous task and restart task expiration manager
    await pending_task.complete()
    if new_task is not None:
        await new_task.move_in_queue()
    await restart_expiration_manager()
