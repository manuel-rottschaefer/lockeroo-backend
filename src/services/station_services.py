"""Provides utility functions for the station management backend."""

# Basics
from datetime import datetime
from typing import Dict, List, Optional
from collections import Counter
import yaml
# Beanie
from beanie import SortDirection
from beanie.operators import In, Near, Set
# Entities
from src.entities.user_entity import User
from src.entities.locker_entity import Locker
from src.entities.session_entity import Session
from src.entities.station_entity import Station
from src.entities.task_entity import Task
# Services
from src.services.auth_services import permission_check
# Models
from src.models.locker_models import (
    LockerModel,
    LockerType,
    LOCKER_TYPES,
    ReducedLockerView,
    LockerTypeAvailabilityView)
from src.models.session_models import (
    ACTIVE_SESSION_STATES, SessionModel,
    SessionState)
from src.models.station_models import (
    StationModel,
    StationState,
    StationType,
    StationView,
    TerminalState)
from src.models.task_models import (
    TaskItemModel,
    TaskState,
    TaskTarget,
    TaskType)
from src.models.permission_models import PERMISSION
# Exceptions
from src.exceptions.locker_exceptions import LockerNotFoundException
from src.exceptions.session_exceptions import InvalidSessionStateException
from src.exceptions.station_exceptions import (
    InvalidTerminalStateException)
from src.exceptions.task_exceptions import TaskNotFoundException
from src.exceptions.locker_exceptions import LockerNotAvailableException
# Services
from src.services.logging_services import logger_service as logger

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


async def get_all_stations(user: User) -> List[StationView]:
    """Returns a list of all installed stations."""
    # 1: Verify permissions
    permission_check([PERMISSION.STATION_VIEW_BASIC], user.doc.permissions)

    # 2: Return stations
    stations: List[StationView] = await StationModel.find_all(
        # StationModel.installed_at < datetime.now()
    ).limit(100).project(StationView).to_list()
    return stations


async def discover(user: User, lat: float, lon: float, radius: int,
                   amount: int) -> List[StationView]:
    """Return a list of stations within a given range around a location"""
    # 1: Verify permissions
    permission_check([PERMISSION.STATION_VIEW_BASIC], user.doc.permissions)

    # 2: Return stations
    stations: List[StationView] = await StationModel.find(
        Near(StationModel.location, lat, lon, max_distance=radius)
    ).limit(amount).project(StationView).to_list()
    return stations


async def get_details(user: User, callsign: str) -> Optional[StationView]:
    """Get detailed information about a station."""
    # 1: Verify permissions
    permission_check([PERMISSION.STATION_VIEW_ADVANCED], user.doc.permissions)

    # 2: station data from the database
    station: StationView = await StationModel.find(
        StationModel.callsign == callsign
    ).project(StationView).first_or_none()
    return station


async def get_station_state(user: User, callsign: str) -> Optional[StationState]:
    """Get the state of a station."""
    # 1: Verify permissions
    permission_check([PERMISSION.STATION_VIEW_ADVANCED], user.doc.permissions)

    # 2: Return station state
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign
    ).first_or_none(),
        callsign=callsign
    )
    return station.station_state


async def get_active_session_count(user: User, callsign: str) -> Optional[int]:
    """Get the amount of currently active sessions at this station."""
    # 1: Verify permissions
    permission_check([PERMISSION.STATION_VIEW_ADVANCED], user.doc.permissions)

    # 2: Find station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign)

    # 3: Return Sessions
    return await SessionModel.find(
        SessionModel.assigned_station == station.id,
        In(SessionModel.session_state,
           ACTIVE_SESSION_STATES),  # pylint: disable=no-member
        fetch_links=True
    ).count()


async def get_locker_by_index(
        user: User, callsign: str, station_index: int) -> Optional[LockerModel]:
    """Get the locker at a station by its index."""
    # 1: Verify permissions
    permission_check([PERMISSION.STATION_VIEW_BASIC], user.doc.permissions)

    # 2: Get the station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign)

    # 3: Get the assigned locker
    locker: Locker = Locker(await LockerModel.find(
        LockerModel.station == station.doc.id,
        LockerModel.station_index == station_index
    ).first_or_none())
    if not locker.exists:
        raise LockerNotFoundException(
            station_callsign=callsign,
            station_index=station_index)
    return locker.doc


async def get_locker_overview(
        user: User, callsign: str) -> List[LockerTypeAvailabilityView]:
    """Determine for each locker type if it is available at the given station."""
    # 1: Verify permissions
    permission_check([PERMISSION.STATION_VIEW_BASIC], user.doc.permissions)

    # 2: Check whether the station exists
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign)

    # 3: Find all active sessions at this station
    available_lockers: List[ReducedLockerView] = await station.get_available_lockers()
    locker_type_counts = Counter(
        locker.locker_type for locker in available_lockers)

    # 4: Create a list of locker availabilities
    locker_availabilities: List[LockerTypeAvailabilityView] = [
        LockerTypeAvailabilityView(
            issued_at=datetime.now(),
            station=callsign,
            locker_type=locker_type,
            is_available=locker_type_counts[locker_type] > 0)
        for locker_type in locker_type_counts
    ]
    return locker_availabilities


async def set_station_state(user: User, callsign: str, station_state: StationState) -> StationView:
    """Set the state of a station."""
    # 1: Verify permissions
    permission_check([PERMISSION.STATION_OPERATE], user.doc.permissions)

    # 2: Get station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign)

    # 3: Modify station state
    await station.register_station_state(station_state)
    return StationView.from_document(station.doc)


async def reset_queue(user: User, callsign: str) -> StationView:
    """Reset the queue of the station by putting all queue
    items in state QUEUED and re-evaluating the queue."""
    # 1: Find the assigned station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign)

    # 2: Get all stale queue items at the station
    tasks: List[TaskItemModel] = await TaskItemModel.find(
        TaskItemModel.assigned_station.id == station.doc.id,  # pylint: disable=no-member
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
        TaskItemModel.task_state == TaskState.PENDING
    ).sort((TaskItemModel.created_at, SortDirection.ASCENDING)).first_or_none()

    # 3: Set all to state QUEUED
    await tasks.update(Set({TaskItemModel.task_state: TaskState.QUEUED}))

    # 4: Re-evaluate the queue
    first_task: Task = Task(tasks[0])
    await first_task.activate()


async def handle_reservation_request(
        user: User, callsign: str, locker_type: str
) -> None:
    """Evaluates a reservation request at a station.
    First checks if the station is available and whether
    a locker of the requested type is available. If so,
    create a reservation task at the station and activate it."""
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_ACTIONS], user.doc.permissions)

    # 2: Find the assigned station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign)

    # 3: Check if the station is currently available
    if station.station_state != StationState.AVAILABLE:
        raise InvalidTerminalStateException(
            station_callsign=callsign,
            expected_states=[StationState.AVAILABLE],
            actual_state=station.station_state,
            raise_http=True)

    # 4: Check if a locker of the requested type is available
    locker_type_map = {locker.name.lower(): locker for locker in LOCKER_TYPES}
    locker_type: LockerType = locker_type_map.get(locker_type.lower(), None)
    available_locker = await Locker.find_available(station, locker_type)
    if not available_locker.exists:
        raise LockerNotAvailableException(
            station_callsign=callsign,
            locker_type=locker_type,
            raise_http=True)

    # 5: Create a reservation task, to be completed by a session creation
    logger.info((
        f"Created reservation for user '{user.doc.fief_id}' "
        f"at locker '#{available_locker.id}'."))
    await Task(await TaskItemModel(
        target=TaskTarget.USER,
        task_type=TaskType.RESERVATION,
        assigned_user=user.doc,
        assigned_station=station.doc,
        assigned_locker=available_locker.doc,
        timeout_states=[SessionState.EXPIRED],
    ).insert()).activate()


async def handle_reservation_cancel_request(
        user: User, callsign: str
) -> None:
    """Evaluates a reservation cancel request at a station.
    First checks if a reservation is currently pending for the user,
    and if so, cancels it."""
    # 1: Verify permissions
    permission_check([PERMISSION.SESSION_ACTIONS], user.doc.permissions)

    # 2: Find the assigned station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign)

    # 3: Find the pending reservation task for this user
    task: Task = Task(await TaskItemModel.find(
        TaskItemModel.target == TaskTarget.USER,
        TaskItemModel.task_type == TaskType.RESERVATION,
        TaskItemModel.task_state == TaskState.PENDING,
        TaskItemModel.assigned_user == user.doc,
        TaskItemModel.assigned_station == station.doc,
        In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
           ACTIVE_SESSION_STATES),
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.ASCENDING
    )).first_or_none())
    if not task.exists:
        raise TaskNotFoundException(
            assigned_station=callsign,
            task_type=TaskType.RESERVATION,
            raise_http=False)

    # 4: Cancel the reservation task
    await task.cancel()


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
    station: Station = Station(
        task.doc.assigned_station,
        callsign=callsign)

    # 3: Get the assigned session
    assert (task.assigned_session is not None
            ), f"Task '#{task.id}' exists but has no assigned session."
    await task.assigned_session.sync()
    session = Session(task.assigned_session)

    # 4: Check whether the station is currently told to await an action
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
        assigned_user=session.assigned_user,
        assigned_station=station.doc,
        assigned_session=session.doc,
        timeout_states=[SessionState.ABORTED],
    ).insert()).activate()

    await task.complete()


async def handle_terminal_state_confirmation(
        callsign: str, confirmed_state: TerminalState):
    """Process a station report about its terminal state."""
    logger.info((
        f"Station '{callsign}' confirmed terminal "
        f"in {confirmed_state}."))

    # 1: Find the affected station
    station: Station = Station(await StationModel.find(
        StationModel.callsign == callsign).first_or_none(),
        callsign=callsign)
    if station.terminal_state == confirmed_state:
        raise InvalidTerminalStateException(
            station_callsign=callsign,
            expected_states=[
                state for state in TerminalState if state != confirmed_state],
            actual_state=confirmed_state)

    # 2: Find the pending task for this station
    pending_task: Task = Task(await TaskItemModel.find(
        TaskItemModel.assigned_station.id == station.id,  # pylint: disable=no-member
        TaskItemModel.target == TaskTarget.TERMINAL,
        TaskItemModel.task_type == TaskType.CONFIRMATION,
        TaskItemModel.task_state == TaskState.PENDING,
        # TODO: Check if required.
        # In(TaskItemModel.assigned_session.session_state,  # pylint: disable=no-member
        #   ACTIVE_SESSION_STATES),
        fetch_links=True
    ).sort((
        TaskItemModel.created_at, SortDirection.DESCENDING
    )).first_or_none())
    if not pending_task.exists:
        raise TaskNotFoundException(
            assigned_station=callsign,
            task_type=TaskType.CONFIRMATION,
            raise_http=False)

    # 3: Register the new state
    await station.register_terminal_state(confirmed_state)

    # 5: Get the assigned session
    await pending_task.doc.fetch_link(TaskItemModel.assigned_session)
    assert (pending_task.doc.assigned_session is not None
            ), f"Task '#{pending_task.id}' has no assigned session."
    session: Session = Session(pending_task.doc.assigned_session)

    if confirmed_state == TerminalState.IDLE:  # Evaluate the next task
        await pending_task.evaluate_next()

    # 6: Complete previous task
    await pending_task.complete()

    # 7: Do not create followup tasks if the session is canceled
    if session.doc.session_state not in ACTIVE_SESSION_STATES:
        return

    # 8: Create next task according to the session context
    if confirmed_state == TerminalState.VERIFICATION:
        await Task(await TaskItemModel(
            target=TaskTarget.TERMINAL,
            task_type=TaskType.REPORT,
            queued_state=session.next_state,
            assigned_user=session.assigned_user,
            assigned_station=station.doc,
            assigned_session=session.doc,
            timeout_states=([SessionState.EXPIRED] if session.doc.timeout_count >= 1
                            else [SessionState.PAYMENT_SELECTED, SessionState.EXPIRED]),
        ).insert()).activate()

    elif confirmed_state == TerminalState.PAYMENT:
        await Task(await TaskItemModel(
            target=TaskTarget.TERMINAL,
            task_type=TaskType.REPORT,
            queued_state=session.next_state,
            assigned_user=session.assigned_user,
            assigned_station=station.doc,
            assigned_session=session.doc,
            timeout_states=([SessionState.EXPIRED] if session.timeout_count >= 1
                            else [session.doc.session_state, SessionState.EXPIRED]),
        ).insert()).activate()

    elif confirmed_state == TerminalState.IDLE:
        # TODO: Find a better way to check if the task is from an expired one
        if pending_task.doc.is_expiration_retry:
            # Create task for user to try the expired action again
            await Task(await TaskItemModel(
                target=TaskTarget.USER,
                task_type=TaskType.REPORT,
                assigned_user=session.assigned_user,
                assigned_station=station.doc,
                assigned_session=session.doc,
                timeout_states=[SessionState.EXPIRED],
            ).insert()).activate()
        else:
            # Create a task to await the unlocking
            await Task(await TaskItemModel(
                target=TaskTarget.LOCKER,
                task_type=TaskType.CONFIRMATION,
                assigned_user=session.assigned_user,
                assigned_station=station.doc,
                assigned_session=session.doc,
                assigned_locker=session.assigned_locker,
                timeout_states=[SessionState.ABORTED],
            ).insert()).activate()

    else:
        raise InvalidTerminalStateException(
            station_callsign=callsign,
            expected_states=[confirmed_state],
            actual_state=confirmed_state
        )
