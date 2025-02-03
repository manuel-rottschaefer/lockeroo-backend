"""
This module describes the database model for actions, which are representations
of events related to a sessionthat are seperately to provide
detailed session history data and better understand special cases.
"""
from dataclasses import dataclass
# Types
from datetime import datetime
from enum import Enum

# Beanie
from beanie import Document, View, Link, before_event, Insert
from beanie import PydanticObjectId as ObjId
from pydantic import Field, PydanticUserError

# Models
from src.models.session_models import SessionModel


class ActionType(str, Enum):
    """A list of actions that a user can do """
    CREATE = "create"
    SELECT_PAYMENT = "selectPayment"
    REQUEST_VERIFICATION = "requestVerification"
    LOCK_AFTER_STASHING = "lockAfterStashing"
    REQUEST_HOLD = "requestHold"
    REQUEST_PAYMENT = "requestPayment"
    LOCK_AFTER_RETRIEVAL = "lockerAfterRetrieval"
    REQUEST_CANCEL = "requestCancel"
    COMPLETE = "complete"


class ActionModel(Document):  # pylint: disable=too-many-ancestors
    """Database representation of a action"""
    # Identification
    id: ObjId = Field(None, alias="_id")

    assigned_session: Link[SessionModel] = Field(
        None, description="The session to which this action belongs."
    )

    # Action Properties
    timestamp: datetime = Field(
        None, description="The timestamp of when this action was registered."
    )

    action_type: ActionType = Field(
        None, description="The type of action expressed as a session state name")

    @ before_event(Insert)
    def add_timestamp(self):
        """Add the timestamp to the document before it is inserted."""
        self.timestamp = datetime.now()

    @ dataclass
    class Settings:
        name = "actions"

    @ dataclass
    class Config:
        json_schema_extra = {
            "assigned_session": "60d5ec49f1d2b2a5d8f8b8b8",
            "timestamp": "2023-10-10T10:00:00",
            "action_type": "create"
        }


class ActionView(View):  # pylint: disable=too-many-ancestors
    """Database representation of a action"""
    id: ObjId = Field(None, alias="_id")
    assigned_session: ObjId

    # Action Properties
    timestamp: datetime
    action_type: ActionType

    @ dataclass
    class Settings:
        source = ActionModel
        projection = {
            "id": "$_id",
            "assigned_session": "$assigned_session",
            "timestamp": "$timestamp",
            "action_type": "$action_type"
        }

    @ dataclass
    class Config:
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "assigned_session": "60d5ec49f1d2b2a5d8f8b8b8",
            "timestamp": "2023-10-10T10:00:00",
            "action_type": "create"
        }


try:
    for model in [ActionModel, ActionView]:
        model.model_json_schema()
except PydanticUserError as exc_info:
    assert exc_info.code == 'invalid-for-json-schema'
