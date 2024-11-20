"""Provides utility functions for the locker management backend."""

# Types
from beanie import SortDirection
from beanie.operators import In

# Entities
from src.entities.station_entity import Station
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker
from src.entities.task_entity import Task

# Models
from src.models.locker_models import LockerModel, LockerStates
from src.models.session_models import SessionModel, SessionStates
from src.models.task_models import TaskStates, TaskTypes

# Services
from src.services.logging_services import logger
from src.services.exceptions import ServiceExceptions
from src.services.action_services import create_action


async def handle_lock_report(call_sign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been closed"""
    # 1: Find the affected locker
    locker: Locker = await Locker().fetch(
        call_sign=call_sign, index=locker_index, with_linked=True)
    if not locker.exists:
        logger.info(ServiceExceptions.LOCKER_NOT_FOUND,
                    station=call_sign, detail=locker_index)

    # 2: Check whether the internal locker state matches the reported situation
    if locker.reported_state != LockerStates.UNLOCKED.value:
        logger.error(f"Locker '{locker.id}' should be unlocked, but is {
                     locker.reported_state}.")
        return

    # 3: Find the station to get its ID
    # TODO: This should be called by the with_links parameter
    await locker.document.fetch_link(LockerModel.parent_station)
    station: Station = Station(locker.parent_station)
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND,
                    station=call_sign)

    # 4: Find the assigned session
    session: Session = await Session().fetch(locker=locker, with_linked=False)

    if not session:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND, locker=locker.id)
        return

    # 5: If those checks pass, update the locker and create an action
    await locker.set_state(LockerStates.LOCKED)
    await create_action(session.id, session.session_state)
    # await session.set_state(await session.next_state)

    # 6: Complete the previous task item
    task_item: Task = await Task().fetch(session=session)
    await task_item.set_state(TaskStates.COMPLETED)

    next_state: SessionStates = await session.next_state
    if next_state == SessionStates.COMPLETED:
        await session.set_state(SessionStates.COMPLETED)
        return

    await Task().create(
        task_type=TaskTypes.USER,
        station=station.document,
        session=session.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.STALE],
        queue=False
    )


async def handle_unlock_confirmation(
        call_sign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been unlocked"""
    # 1: Find the affected locker
    locker: Locker = await Locker().fetch(
        call_sign=call_sign, index=locker_index, with_linked=True)
    if not locker.exists:
        logger.info(ServiceExceptions.LOCKER_NOT_FOUND,
                    station=call_sign, detail=locker_index)

    # 2: Check whether the internal locker state matches the reported situation
    if locker.reported_state != LockerStates.LOCKED.value:
        logger.error(f"Locker '{locker.id}' should be locked, but is {
                     locker.reported_state}.")
        return

    # 3: Find the station to get its ID
    # TODO: This should be called by the with_links parameter
    await locker.document.fetch_link(LockerModel.parent_station)
    station: Station = Station(locker.parent_station)
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND,
                    station=call_sign)

    # 4: Find the assigned session
    accepted_session_states = [SessionStates.VERIFICATION,
                               SessionStates.PAYMENT,
                               SessionStates.HOLD]
    session: Session = await Session().fetch(locker=locker, with_linked=True)
    if not session.exists:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND,
                    station=call_sign)
        return

    if session.session_state not in accepted_session_states:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session.id, detail=session.session_state)
        return

    # 5: Update locker and session states
    await locker.set_state(LockerStates.UNLOCKED)

    # 6: Complete the current active session
    task: Task = await Task().fetch(session=session)
    await task.set_state(TaskStates.COMPLETED)

    # 7: Create a queue item for the user
    await Task().create(
        task_type=TaskTypes.USER,
        station=station.document,
        session=session.document,
        queued_state=await session.next_state,
        timeout_states=[SessionStates.STALE],
        queue=False
    )

    # 8: Create action entry
    await create_action(session.id, session.session_state)
