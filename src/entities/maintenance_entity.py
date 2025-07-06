"""
Lockeroo.maintenance_entity
-------------------------
This module provides the Maintenance Entity class

Key Features:
    - Provides a functionality wrapper for Beanie Documents

Dependencies:
    - beanie
"""
# Basics
from datetime import datetime, timezone
# Types
from beanie import PydanticObjectId as ObjId
# Entities
from src.entities.entity import Entity
# Models
from lockeroo_models.maintenance_models import MaintenanceSessionModel, MaintenanceSessionState


class Maintenance(Entity):
    """
    Lockeroo.Maintenance
    -------
    A class representing a maintenance event.
    Maintenance scopes range from regular cleaning to technical work at the station

    Key Features:
    - `__init__`: Initializes a maintenance object
    - 'create': Creates a maintenance object and adds it to the database
    """
    doc: MaintenanceSessionModel

    def __init__(self):
        super().__init__()

    @classmethod
    async def create(
        cls,
        station_id: ObjId,
        staff_id: ObjId
    ):
        """Creates a maintenance document in the database

        Args:
            - self [Maintenance]: The maintenance Entity

        Returns:
            Maintenance

        Raises:
            -

        Example:
            >>> maintenance.create()
            Maintenance
        """
        instance = cls()
        instance.doc = MaintenanceSessionModel(
            assigned_station=station_id,
            assigned_staff=staff_id,
            state=MaintenanceSessionState.SCHEDULED,
            scheduled_for=datetime.now(timezone.utc),
        )
        await instance.doc.insert()
        return instance
