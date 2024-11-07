'''Utilities for the session model'''

# Basics
from datetime import datetime, timedelta
import asyncio

# Types
from typing import List, Dict
from beanie import PydanticObjectId as ObjId
from beanie import After

# Models
from src.models.session_models import SessionModel, SessionPaymentTypes, SessionStates
from src.models.action_models import ActionModel
from src.models.locker_models import LockerModel
from src.models.queue_models import QueueItemModel, QueueStates

# Services
from ..services.logging_services import logger
from ..services.exceptions import ServiceExceptions


class Session():
    '''Add behaviour to a session instance.'''

    def __getattr__(self, name):
        '''Delegate attribute access to the internal document.'''
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        '''Delegate attribute setting to the internal document, except for 'document' itself.'''
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    def __init__(self, document: SessionModel = None):
        super().__init__()
        self.document = document

    @classmethod
    async def fetch(
        cls,
        session_id: ObjId = None,
        user_id: ObjId = None,
        station_id: ObjId = None,
        locker_id: ObjId = None,
    ):
        '''Create a Session instance and fetch the object asynchronoysly.'''
        instance = cls()
        if session_id is not None:
            instance.document = await SessionModel.get(session_id)
            return instance

        if None not in [user_id, station_id, locker_id]:
            instance.document = SessionModel(
                assigned_user=user_id,
                assigned_station=station_id,
                assigned_locker=locker_id,
                state=SessionStates.CREATED,
                createdTS=datetime.now(),
            )
            await instance.document.insert()
            logger.debug(
                f"Created session '{instance.id}' for user '{
                    user_id}' at station '{station_id}'"
            )
            return instance

        if locker_id is not None:
            session: SessionModel = await SessionModel.find_one(
                SessionModel.assigned_locker == locker_id,
                SessionModel.session_state != SessionStates.COMPLETED
            )
            if not session:
                logger.info(
                    f"No active session found at locker '{locker_id}'.")
            instance.document = session
            return instance
        else:
            logger.error(
                "Failed to initialize Session, no valid parameters provided.")
            return None

    ### Calculated Properties ###

    @property
    def exists(self) -> bool:
        '''Check wether this object exists.'''
        return self.document is not None

    @property
    def expiration_duration(self) -> int:
        '''Returns the amount of seconds after the session expires in the curent state.'''
        return 0

    @property
    def has_expired(self) -> bool:
        '''Return wether the session has already expired.'''
        return False

    @property
    def total_duration(self) -> int:
        '''Returns the amount of seconds between session creation and completion or now.'''
        return 0

    @property
    async def active_duration(self) -> int:
        '''Returns the amount of seconds the session has been active until now,
        i.e time that the user gets charged for.'''

        # Collect all actions of the session
        active_duration: timedelta = timedelta(minutes=0)
        cycle_start: datetime = None

        # TODO: Is a list required here?
        resume_states: List[SessionStates] = [SessionStates.ACTIVE]

        hold_states: List[SessionStates] = [
            SessionStates.HOLD,
            SessionStates.PAYMENT_QUEUED,
        ]

        # Sum up time between all locked cycles
        async for action in ActionModel.find(ActionModel.session_id == self.id).sort(
            ActionModel.timestamp
        ):
            if action.action_type in resume_states:
                cycle_start = action.timestamp
            elif action.action_type in hold_states:
                active_duration += action.timestamp - cycle_start

        return active_duration

    @property
    async def timeout_amount(self) -> int:
        ''' Return the number of times that this session already timed out.'''
        return await QueueItemModel.find(
            QueueItemModel.assigned_session == self.document.id,
            QueueItemModel.queue_state == QueueStates.EXPIRED
        ).count()

    @property
    async def next_state(self):
        '''Return the next logical state of the session.'''
        state_map: dict = {
            SessionStates.CREATED: SessionStates.PAYMENT_SELECTED,
            SessionStates.PAYMENT_SELECTED: SessionStates.VERIFICATION_QUEUED,
            SessionStates.VERIFICATION_QUEUED: SessionStates.VERIFICATION_PENDING,
            SessionStates.VERIFICATION_PENDING: SessionStates.STASHING,
            SessionStates.STASHING: SessionStates.ACTIVE,
            SessionStates.ACTIVE: SessionStates.PAYMENT_QUEUED,
            SessionStates.PAYMENT_QUEUED: SessionStates.PAYMENT_PENDING,
            SessionStates.PAYMENT_PENDING: SessionStates.RETRIEVAL,
            SessionStates.RETRIEVAL: SessionStates.COMPLETED,
        }
        return state_map.get(self.session_state)

    async def set_state(self, state: SessionStates, notify: bool = True):
        '''Update the current state of a session.'''
        try:
            self.document.session_state = state
            if notify:
                await self.document.replace()
            else:
                await self.document.replace(skip_actions=[After])

            logger.debug(
                f"Session '{self.id}' updated to state '{self.session_state}'."
            )

        except (ValueError, TypeError) as e:
            logger.error(f"Failed to update state of session '{
                         self.id}': {e}.")

    async def assign_payment_method(self, method: SessionPaymentTypes):
        '''Assign a payment method to a session.'''
        try:
            self.document.payment_method = method
            await self.replace(skip_actions=[After])
            logger.info(
                f"Payment method '{
                    self.payment_method}' assigned to session '{self.id}'."
            )
        except (ValueError, TypeError) as e:
            logger.error(
                f"Failed to assign payment method {
                    method} to session {self.id}: {e}"
            )

    async def get_price(self) -> int:
        '''Calculate the total cost of a session in cents.
        This can only be conducted while the session is still queued for payment.'''
        # 1: Check if session queued for payment
        if self.session_state != SessionStates.PAYMENT_QUEUED:
            # TODO: Throw an error here
            return 0.0

        # 2: Get the locker assigned to this session
        locker: LockerModel = await LockerModel.get(self.assigned_locker)
        if not locker:
            # TODO: Raise error here
            pass

        # 3: Get the pricing model for this session
        # TODO: Add type here
        pricing_model = locker.type.pricing

        # 4:Calculate the total cost
        calculated_price: int = await pricing_model.minute_rate * (
            self.document.active_duration / 60
        )

        # 5: Assure that price is withing bounds
        calculated_price = min(
            max(calculated_price, pricing_model.min_price), pricing_model.max_price
        )

        logger.info(
            "Calculated price of %d cents for session '%s'.", calculated_price, self.id
        )

        return calculated_price

    async def register_expiration(self, seconds: int):
        '''Register an expiration handler. This waits until the expiration duration has passed and then fires up the expiration handler.'''
        # 1 Register the expiration handler
        await asyncio.sleep(int(seconds))

        # 2: Update the own object. This is required.
        session_item: Session = Session(await SessionModel.get(self.document.id))

        # 2: After the expiration time, fire up the expiration handler if required
        pending_states: List[SessionStates] = {
            SessionStates.VERIFICATION_PENDING,
            SessionStates.PAYMENT_PENDING,
            SessionStates.STASHING,
            SessionStates.HOLD,
            SessionStates.RETRIEVAL
        }
        if session_item.document.session_state in pending_states:
            logger.debug(f'Registered expiration after {seconds} seconds.')
            await self.handle_expiration()

    async def handle_expiration(self) -> None:
        '''Checks wether the session has entered a state where the user needs to conduct an
        action within a limited time. If that time has been exceeded but the action has not been
        completed, the session has to be expired and the user needs to request a new one
        '''
        # 1: Update the own object. This is required.
        session_item: Session = Session(await SessionModel.get(self.document.id))

        # TODO: Maybe we should introduce a new session state 'exited' that only enters if a locker is left open.
        # This would make finding open lockers easier.
        state_map: Dict[SessionStates, SessionStates] = {
            SessionStates.STASHING: SessionStates.EXPIRED,
            SessionStates.HOLD: SessionStates.COMPLETED,
            SessionStates.RETRIEVAL: SessionStates.COMPLETED
        }

        # 3: Update session and queue item states
        await session_item.set_state(state_map[session_item.session_state], True)
        await session_item.set_state(QueueStates.EXPIRED)

        # 4: Create a logging message
        logger.info(
            ServiceExceptions.SESSION_EXPIRED,
            session=session_item.id,
            detail=session_item.session_state,
        )
