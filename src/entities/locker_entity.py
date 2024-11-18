"""Utilities for the locker model"""

# Types
from beanie import PydanticObjectId as ObjId
from beanie.operators import Set

# Models
from src.models.locker_models import LockerModel, LockerStates

# Services
from src.services.logging_services import logger
from src.services.mqtt_services import fast_mqtt


class Locker():
    """Add behaviour to a locker instance."""

    def __getattr__(self, name):
        """Delegate attribute access to the internal document"""
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the internal document, except for 'document' itself"""
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    def __init__(self, document: LockerModel = None):
        super().__init__()
        self.document = document

    @classmethod
    async def fetch(
        cls,
        locker_id: ObjId = None,
        station_id: ObjId = None,
        index: int = None
    ):
        """Create a Locker instance and fetch the object asynchronously."""
        instance = cls()

        if locker_id is not None:
            instance.document = await LockerModel.get(locker_id)
        elif None not in [station_id, index]:
            locker: LockerModel = await LockerModel.find_one(
                LockerModel.parent_station == station_id,
                LockerModel.station_index == index
            )
            if not locker:
                logger.info("Locker '#%s' not found at station '%s'.",
                            index, station_id)

            instance.document = locker

        return instance

    async def set_state(self, state: LockerStates):
        """Update the reported (actual) locker state"""
        await self.document.update(Set({LockerModel.reported_state: state}))

    async def instruct_unlock(self, call_sign: str):
        # TODO: This function is being called only once, evaluate alternative locations
        """Send a message to the station to unlock the locker."""
        fast_mqtt.publish(
            f'stations/{call_sign}/locker/{self.station_index}/instruct', 'UNLOCK')
