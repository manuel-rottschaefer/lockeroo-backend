'''
This module describes the database model for actions, which are representations
of events related to a sessionthat are seperately to provide
detailed session history data and better understand special cases.
'''

# Basics
from datetime import datetime

# Types
import dataclasses
from pydantic import Field

# Beanie
from beanie import Document, View
from beanie import PydanticObjectId as ObjId

# Models
from src.models.session_models import SessionStates


class ActionModel(Document):  # pylint: disable=too-many-ancestors
    '''Database representation of a action'''

    # Identification
    id: ObjId = Field(alias="_id", default=None)
    assigned_session: ObjId = Field(
        None, description="The session to which this action belongs."
    )
    # assigned_user: ObjId

    # Action Properties
    timestamp: datetime = Field(
        None, description="The timestamp of when this action was registered."
    )
    action_type: SessionStates

    @dataclasses.dataclass
    class Settings:
        '''Name in database'''

        name = "actions"


class ActionView(View):  # pylint: disable=too-many-ancestors
    '''Database representation of a action'''

    # Identification
    id: ObjId = Field(alias="_id", default=None)
    assigned_session: ObjId = Field(
        None, description="The assigned session to this action."
    )
    assigned_user: ObjId = Field(
        None,
        description="The assigned user to the session of this action. Is this even required?",
    )

    # Action Properties
    timestamp: datetime = Field(
        None, description="The timestamp at which the action was registered."
    )
    action_type: SessionStates = Field(
        None, description="The type of action that has been registered."
    )

    @dataclasses.dataclass
    class Settings:
        '''Name in database'''

        name = "actions"
