"""
This module describes the database model for actions, which are representations
of events related to a sessionthat are seperately to provide
detailed session history data and better understand special cases.
"""

# Basics
from datetime import datetime

# Types
import dataclasses
from pydantic import Field

# Beanie
from beanie import Document, Link, View
from beanie import PydanticObjectId as ObjId

# Models
from src.models.session_models import SessionModel, SessionStates


class ActionModel(Document):  # pylint: disable=too-many-ancestors
    """Database representation of a action"""
    # Identification
    id: ObjId = Field(alias="_id", default=None)

    assigned_session: Link[SessionModel] = Field(
        None, description="The session to which this action belongs."
    )

    # Action Properties
    timestamp: datetime = Field(
        None, description="The timestamp of when this action was registered."
    )
    action_type: str = Field(
        None, description="The type of action expressed as a session state name")

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "actions"


class ActionView(View):  # pylint: disable=too-many-ancestors
    """Database representation of a action"""

    # Identification
    id: ObjId = Field(alias="_id", default=None)
    assigned_session: ObjId = Field(
        None, description="The assigned session to this action."
    )

    # Action Properties
    timestamp: datetime = Field(
        None, description="The timestamp at which the action was registered."
    )
    action_type: SessionStates = Field(
        None, description="The type of action that has been registered."
    )

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "actions"
