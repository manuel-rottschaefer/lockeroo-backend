"""Provides utility functions for the station management backend."""

# Basics
from typing import List

# API services
from fastapi import HTTPException
from beanie.operators import Near

# Beanie
from beanie.operators import Set

# Entities
from src.entities.station_entity import Station
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker
from src.entities.task_entity import Task

# Models
from src.models.locker_models import LockerModel, LockerStates
from src.models.session_models import SessionModel, SessionStates
from src.models.task_models import TaskItemModel, TaskStates, TaskTypes
from src.models.station_models import (StationLockerAvailabilities, StationModel,
                                       StationView, StationStates, TerminalStates)

# Services
from src.services.exceptions import ServiceExceptions
from src.services.logging_services import logger


async def discover(lat: float, lon: float, radius: int,
                   amount: int) -> List[StationView]:
    """Return a list of stations within a given range around a location"""
    stations: List[StationView] = await StationModel.find(
        Near(StationModel.location, lat, lon, max_distance=radius)
    ).limit(amount).to_list()
    return stations


async def get_details(call_sign: str) -> StationView:
    """Get detailed information about a station."""
    # Get station data from the database
    station: Station = await Station().fetch(call_sign=call_sign)
    if not station:
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.STATION_NOT_FOUND)

    return station.document


async def get_active_session_count(call_sign: str) -> int:
    """Get the amount of currently active sessions at this station."""
    station: Station = await Station().fetch(call_sign=call_sign)
    if not station:
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.STATION_NOT_FOUND)

    return await SessionModel.find(
        SessionModel.assigned_station == station.id,
        SessionModel.session_state.is_active is True  # pylint: disable=no-member
    ).count()


async def get_locker_by_index(call_sign: str, locker_index: int):
    """Get the locker at a station by its index."""
    station: Station = await Station().fetch(call_sign=call_sign)
    return await Locker().fetch(station=station.id, index=locker_index)


async def get_locker_overview(call_sign: str) -> StationLockerAvailabilities:
    """Determine for each locker type if it is available at the given station."""

    # 1: Check whether the station exists
    station: Station = await Station().fetch(call_sign=call_sign)

    if not station:
        logger.warning("Station '%s' does not exist.", call_sign)
        raise HTTPException(
            status_code=404, detail=ServiceExceptions.STATION_NOT_FOUND.value)

    # 2: Create the object
    availability = StationLockerAvailabilities()

    # 3: Loop over each locker type to find the amount of lockers
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
    station: Station = Station().fetch(call_sign=call_sign)
    await station.set_station_state(station_state)
    return station.document


async def reset_queue(call_sign: str) -> StationView:
    """Reset the queue of the station by putting all queue
    items in state QUEUED and re-evaluating the queue."""
    # 1: Get the station
    station: Station = await Station().fetch(call_sign=call_sign)

    # 2: Get all stale queue items at the station
    tasks: List[TaskItemModel] = await TaskItemModel.find(
        TaskItemModel.assigned_station == station.id,
        TaskItemModel.task_state == TaskStates.PENDING
    ).sort(TaskItemModel.created_ts)

    # 3: Set all to state QUEUED
    await tasks.update(Set({TaskItemModel.task_state: TaskStates.QUEUED}))

    # 3: Re-evaluate the queue
    first_task: Task = Task(tasks[0])
    await first_task.activate()


async def handle_terminal_report(
        call_sign: str,
        expected_session_state: SessionStates,
        expected_terminal_state: TerminalStates
) -> None:
    """This handler processes reports of completed actions at a station.
        It verifies the authenticity of the report and then updates the state
        values for the station and the assigned session as well as notifies
        the client so that the user can proceed. """
    task: Task = await Task().find(
        call_sign=call_sign,
        task_type=TaskTypes.USER,
        task_state=TaskStates.PENDING)
    await task.fetch_links()

    session = Session(task.assigned_session)
    await session.fetch_links()

    if task.assigned_session.session_state != expected_session_state:
        # TODO: Implement logger for warnings
        logger.warning(
            f"Session {task.assigned_session.id} is in wrong state.")
        return

    # 3: Check whether the station is currently told to await an action
    station: Station = Station(session.assigned_station)
    if station.terminal_state != expected_terminal_state:
        logger.info(ServiceExceptions.INVALID_TERMINAL_STATE,
                    station=call_sign, detail=station.terminal_state)
        return

    # 4: Find the locker that belongs to this session
    locker: Locker = Locker(session.assigned_locker)

    # 5: Set terminal state to idle
    await station.set_terminal_state(TerminalStates.IDLE)
    # await session.set_state(await session.next_state)

    # 6: Instruct the locker to open
    await locker.set_state(LockerStates.UNLOCKED)

    # 7: Set the verification/payment queue item to completed
    await task.set_state(TaskStates.COMPLETED)

    # 8: Create a new queue item for the station to report the unlock
    await Task().create(
        task_type=TaskTypes.STATION,
        station=station.document,
        session=session.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.ABORTED],
        has_queue=False
    )


async def handle_terminal_mode_confirmation(call_sign: str, _mode: str):
    """This handler processes reports of stations whose terminals entered an active state.
    It verifies the authenticity and then notifies the client about the new state."""
    # 1: Get the station object
    station: StationModel = await StationModel.find_one(
        StationModel.call_sign == call_sign
    )
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND, call_sign)
