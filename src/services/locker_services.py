"""Provides utility functions for the locker management backend."""

# Types
from beanie import PydanticObjectId as ObjId
from beanie import SortDirection
from beanie.operators import In

# Entities
from src.entities.station_entity import Station
from src.entities.session_entity import Session
from src.entities.locker_entity import Locker
from src.entities.queue_entity import QueueItem

# Models
from src.models.locker_models import LockerModel, LockerStates
from src.models.session_models import SessionModel, SessionStates
from src.models.station_models import StationModel
from src.models.queue_models import QueueStates

# Services
from src.services.logging_services import logger
from src.services.exceptions import ServiceExceptions
from src.services.action_services import create_action


async def find_available_locker(
        station_id: ObjId, locker_type: str) -> LockerModel:
    """This methods handles the locker selection process at a station"""
    # Try to find a locker that suits all requirements
    # TODO: Prioritize open lockers from expired sessions
    locker: LockerModel = await LockerModel.find(
        LockerModel.parent_station == station_id,
        LockerModel.locker_type.name == locker_type
    ).sort(LockerModel.total_session_count).limit(1).to_list()

    if not locker:
        logger.info(ServiceExceptions.LOCKER_NOT_AVAILABLE,
                    station=station_id)
        return None

    return locker[0]


async def handle_lock_report(call_sign: str, locker_index: int) -> None:
    # TODO: Adjust logging escalation level for station reports??
    """Process and verify a station report that a locker has been closed"""
    # 1: Find the station to get its ID
    station = Station(await StationModel.find_one(StationModel.call_sign == call_sign))
    if not station:
        return False

    # 2: Find the affected locker
    locker: Locker = await station.get_locker(locker_index)
    if not locker:
        logger.error(f"Locker '{locker.id}' should be locked, but is {
                     locker.reported_state}.")
        return False

    # 3: Check whether the internal locker state matches the reported situation
    if locker.reported_state != LockerStates.UNLOCKED.value:
        logger.error(f"Mismatch between internal locker state and \
                        reported state by station for locker '{locker.id}'.")
        return False

    # 4: Find the assigned session
    active_session_states = [SessionStates.STASHING,
                             SessionStates.RETRIEVAL,
                             SessionStates.HOLD]
    session: Session = Session(await SessionModel.find(
        SessionModel.assigned_locker == locker.id,
        In(SessionModel.session_state, active_session_states)
    ).sort((SessionModel.created_ts, SortDirection.DESCENDING)).first_or_none()
    )
    if not session:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND, locker=locker.id)
        return

    # 5: If those checks pass, update the locker and session state
    await locker.set_state(LockerStates.LOCKED)
    await session.set_state(await session.next_state)

    # 6: Complete the queue item
    queue_item: QueueItem = await QueueItem().fetch(session_id=session.id)
    await queue_item.set_state(QueueStates.COMPLETED)

    # 7: Create an action for this
    await create_action(session.id, session.session_state)


async def handle_unlock_confirmation(station_callsign: str, locker_index: int) -> None:
    """Process and verify a station report that a locker has been closed"""

    # 1: Find the station to get its ID
    station: Station = await Station().fetch(call_sign=station_callsign)
    if not station:
        logger.info(ServiceExceptions.STATION_NOT_FOUND,
                    station=station_callsign)

    # 2: Find the affected locker
    locker: Locker = await Locker().fetch(station_id=station.id, index=locker_index)
    if not locker:
        logger.info(ServiceExceptions.LOCKER_NOT_FOUND,
                    station=station_callsign, detail=locker_index)

    # 3: Check whether the internal locker state matches the reported situation
    if locker.reported_state != LockerStates.LOCKED.value:
        logger.error(f"Locker '{locker.id}' should be locked, but is {
                     locker.reported_state}.")
        return False

    # 4: Find the assigned session
    accepted_session_states = [SessionStates.VERIFICATION,
                               SessionStates.PAYMENT,
                               SessionStates.HOLD]
    session: Session = Session(await SessionModel.find(
        SessionModel.assigned_locker == locker.id,
    ).sort((SessionModel.created_ts, SortDirection.DESCENDING)).first_or_none()
    )
    if not session:
        logger.info(ServiceExceptions.SESSION_NOT_FOUND,
                    station=station_callsign)
        return

    assert await session.exists
    if session.session_state not in accepted_session_states:
        logger.info(ServiceExceptions.WRONG_SESSION_STATE,
                    session=session.id, detail=session.session_state)
        return

    # 5: Update locker and session states
    await locker.set_state(LockerStates.UNLOCKED)

    await QueueItem().create(station_id=station.id,
                             session_id=session.id,
                             queued_state=await session.next_state,
                             timeout_state=SessionStates.STALE,
                             skip_eval=True
                             )

    # 7: Create action entry
    await create_action(session.id, session.session_state)
