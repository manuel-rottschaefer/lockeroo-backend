"""This module provides utilities for  database for maintenance events."""

# Basics
from datetime import datetime

# FastAPI
from fastapi import HTTPException

# Types
from beanie import PydanticObjectId as ObjId

# Models
from src.models.maintenance_models import MaintenanceModel, MaintenanceStates

# Services
from src.services.logging_services import logger
from src.services.exceptions import ServiceExceptions


class Maintenance():
    """Add behaviour to a maintenance instance."""

    def __getattr__(self, name):
        """Delegate attribute access to the internal document."""
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the internal document, except for 'document' itself."""
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    def __init__(self, document: MaintenanceModel = None):
        super().__init__()
        self.document = document

    @classmethod
    async def fetch(
        cls,
        maintenance_id: ObjId = None,
        station_id: ObjId = None,
        with_linked: bool = False
    ):
        """Create a Session instance and fetch the object async."""
        instance = cls()
        if maintenance_id is not None:
            instance.document = await MaintenanceModel.get(maintenance_id)

        elif station_id is not None:
            instance.document = await MaintenanceModel.find_one(
                MaintenanceModel.assigned_station == station_id,
                fetch_links=with_linked
            )

        if not instance.exists:
            logger.info(ServiceExceptions.STATION_NOT_FOUND,
                        session=station_id)
            raise HTTPException(
                status_code=404, detail=ServiceExceptions.STATION_NOT_FOUND.value
            )
        return instance

    @classmethod
    async def create(
        cls,
        station_id: ObjId,
        staff_id: ObjId
    ):
        '''Create a new maintenance event and insert it into the database.'''
        instance = cls()
        instance.document = MaintenanceModel(
            assigned_station=station_id,
            assigned_staff=staff_id,
            state=MaintenanceStates.SCHEDULED,
            scheduled_for=datetime.now(),
        )
        await instance.document.insert()
        return instance
