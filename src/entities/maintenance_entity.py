"""This module provides utilities for  database for maintenance events."""
# Basics
from datetime import datetime
# Types
from beanie import PydanticObjectId as ObjId
# Entities
from src.entities.entity_utils import Entity
# Models
from src.models.maintenance_models import MaintenanceModel, MaintenanceState


class Maintenance(Entity):
    """Add behaviour to a maintenance instance."""
    doc: MaintenanceModel

    @classmethod
    async def create(
        cls,
        station_id: ObjId,
        staff_id: ObjId
    ):
        """Create a new maintenance event and insert it into the database."""
        instance = cls()
        instance.doc = MaintenanceModel(
            assigned_station=station_id,
            assigned_staff=staff_id,
            state=MaintenanceState.SCHEDULED,
            scheduled_for=datetime.now(),
        )
        await instance.doc.insert()
        return instance
