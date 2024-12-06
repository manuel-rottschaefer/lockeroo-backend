"""This module provides the Models for review management."""
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
from src.models.session_models import SessionModel


class ReviewModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a review in the database"""

    # Identification
    id: ObjId = Field(alias="_id")
    assigned_session: Link[SessionModel] = Field(
        description="The session to which the review refers to.")

    submitted_ts: datetime

    experience_rating: int = Field(
        ge=1, le=5, description="Rating of the overall experience."
    )
    cleanliness_rating: int = Field(
        ge=1, le=5, description="Rating of the cleanliness of the locker."
    )
    details: str = Field(
        description="Written feedback on the session. Should not be made public."
    )

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "reviews"


class ReviewView(View):  # pylint: disable=too-many-ancestors
    """View of the Review Model"""

    # Identification
    id: ObjId = Field(alias="_id")
    assigned_session: ObjId

    submitted_ts: datetime

    experience_rating: int = Field(
        ge=1, le=5, description="Rating of the overall experience"
    )
    cleanliness_rating: int = Field(
        ge=1, le=5, description="Rating of the cleanliness of the locker"
    )
    details: str = Field(
        description="Written feedback on the session. Should not be made public."
    )
