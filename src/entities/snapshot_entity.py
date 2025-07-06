"""
Lockeroo.action_entity
-------------------------
This module provides the Action Entity class

Key Features:
    - Provides a functionality wrapper for Beanie Documents

Dependencies:
    - typing
"""
# Basics
from typing import Union
# Entities
from src.entities.entity import Entity
# Models
from lockeroo_models.snapshot_models import SnapshotModel, SnapshotView
# Services
from src.services.websocket_services import websocketmanager


class Snapshot(Entity):
    """
    Lockeroo.Action
    -------
    A class representing an action initiated by a user.
    This represents typical activities like starting sessions, verifying payment
    or opening lockers. Logged actions are used to provide support on problems with sessions
    and for analytical benefits.

    Key Features:
    - `__init__`: Initializes a class object and assigns task logic to the document.
    """
    doc: Union[SnapshotModel]

    def __init__(self, document=None):
        super().__init__(document)
        self._add_handlers()

    def _add_handlers(self):
        """Add handlers to the document"""
        async def handle_snap_creation(snapshot: SnapshotModel):
            """Handle the creation of an action"""
            await websocketmanager.send_text(
                snapshot.assigned_session.id,
                SnapshotView.from_document(snapshot).model_dump())

        SnapshotModel.handle_creation = handle_snap_creation
