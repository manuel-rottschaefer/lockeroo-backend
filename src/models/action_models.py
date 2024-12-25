"""
This module describes the database model for actions, which are representations
of events related to a sessionthat are seperately to provide
detailed session history data and better understand special cases.
"""
# Types
import dataclasses
# Basics
from datetime import datetime

# Beanie
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import View
from pydantic import Field

# Models
from src.models.session_models import SessionModel, SessionState


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
    # TODO: For now this is expressed as a session state
    action_type: str = Field(
        None, description="The type of action expressed as a session state name")

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "actions"


class ActionView(View):  # pylint: disable=too-many-ancestors
    """Database representation of a action"""

    # Identification
    id: ObjId = Field(None, alias="_id",)
    assigned_session: ObjId = Field(
        description="The assigned session to this action."
    )

    # Action Properties
    timestamp: datetime = Field(
        None, description="The timestamp at which the action was registered."
    )
    action_type: SessionState = Field(
        None, description="The type of action that has been registered."
    )
