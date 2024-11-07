'''Utilities for the station model'''

# Basics
from beanie import PydanticObjectId as ObjId

# Entities
from src.entities.locker_entity import Locker

# Models
from src.models.session_models import SessionModel, SessionStates
from src.models.station_models import StationModel, StationStates, TerminalStates
from src.models.locker_models import LockerModel

# Services
from ..services.exceptions import ServiceExceptions

# Logging
from ..services.logging_services import logger


class Station():
    '''Adds behaviour for a station instance.'''

    def __getattr__(self, name):
        '''Delegate attribute access to the internal document.'''
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        '''Delegate attribute setting to the internal document, except for 'document' itself'''
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    def __init__(self, document: StationModel = None):
        super().__init__()
        self.document = document

    @classmethod
    async def fetch(cls, station_id: ObjId = None, call_sign: str = None):
        '''Create a Station instance and fetch the object asynchronously.'''
        instance = cls()

        if station_id is not None:
            instance.document = await StationModel.get(station_id)
        elif call_sign is not None:
            instance.document = await StationModel.find_one(StationModel.call_sign == call_sign)
        else:
            logger.error("Failed to initialize Station Entity.")

        if instance.document is None:
            logger.error(
                "Failed to initialize Station Entity: No document found.")
            raise ValueError("Station document could not be found.")

        return instance

    ### Attributes ###
    @property
    async def total_completed_session_count(self) -> int:
        '''Get the total amount of sessions conducted at this station, without active ones.'''
        session_count: int = await SessionModel.find(
            SessionModel.assigned_station == self.document.id,
            SessionModel.session_state == SessionStates.COMPLETED
        ).count()
        return session_count

    @property
    async def active_session_count(self) -> int:
        '''Get the total amount of currently active stations at this station.'''
        session_count: int = await SessionModel.find(
            SessionModel.assigned_station == self.document.id,
            SessionModel.session_state != SessionStates.COMPLETED
        ).count()
        return session_count

    ### Locker management ###

    async def get_locker(self, index: int) -> Locker:
        '''Find a locker at a station by index.'''
        # 1: Find the locker
        return Locker(await
                      LockerModel.find_one(
                          LockerModel.parent_station == self.id,
                          LockerModel.station_index == index,
                      )
                      )

    async def find_available_locker(self, locker_type: str) -> LockerModel:
        '''This methods handles the locker selection process at a station.'''
        # Try to find a locker that suits all requirements
        # TODO: Prioritize open lockers from expired sessions
        locker: LockerModel = await LockerModel.find(
            LockerModel.parent_station == self.id,
            LockerModel.locker_type.name == locker_type
        ).sort(LockerModel.total_session_count).limit(1).to_list()

        if not locker:
            logger.info(ServiceExceptions.LOCKER_NOT_AVAILABLE,
                        station=self.id)
            return None

        logger.debug(f"Identified locker at station '{self.id}'")
        return locker[0]

    ### Terminal setters ###

    async def set_station_state(
        self: StationModel, new_state: StationStates
    ) -> StationStates:
        '''Update the state of a station.
        No checks are performed here, as the request is assumed to be valid.'''
        self.document.station_state = new_state
        await self.replace(skip_actions=['notify_terminal_state'])
        logger.debug("Station '%s' state set to '%s'.",
                     self.call_sign, self.station_state.value)
        return new_state

    async def set_terminal_state(
        self: StationModel, terminal_state: TerminalStates = None, session_state: SessionStates = None
    ) -> StationStates:
        '''Update the terminal state of a station. This function either accepts a TerminalState or a SessionState. '''
        if terminal_state is None and session_state is not None:
            session_to_terminal_map: dict[SessionStates, TerminalStates] = {
                SessionStates.VERIFICATION_PENDING: TerminalStates.VERIFICATION,
                SessionStates.PAYMENT_PENDING: TerminalStates.PAYMENT
            }
            if session_state in session_to_terminal_map:
                terminal_state = session_to_terminal_map[session_state]

        self.document.terminal_state = terminal_state

        await self.document.replace(skip_actions=['notify_station_state'])
        logger.debug(
            f"Station '{self.call_sign}' terminal state awaiting '{
                self.terminal_state.value}'."
        )
        return terminal_state

    async def increase_completed_sessions_count(self: StationModel):
        '''Increase the count of completed sessions at the station.
        No checks are performed here, as the request is assumed to be valid.'''
        self.document.total_sessions += 1
        await self.replace()
