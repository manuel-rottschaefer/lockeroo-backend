"""Models for users."""

# Types
from typing import List, Optional
from uuid import UUID

# Beanie
from beanie import Document
from beanie import PydanticObjectId as ObjId
from pydantic import Field


class UserModel(Document):
    """Representation of a user in the database"""
    id: ObjId = Field(alias='_id')
    fief_id: UUID = Field(description="User ID in fief.")

    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")

    total_sessions: int = Field(
        0, description="Total amount of completed sessions")
    total_session_duration: int = Field(
        0, description="Total seconds of completed session duration")

    cities: List[str] = Field(
        [''], description="List of cities where user was serviced.")
