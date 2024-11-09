"""
Review Models
"""

# Types
import dataclasses

# Basics
from datetime import datetime
from typing import Optional

# Beanie
from beanie import Document, View
from beanie import PydanticObjectId as ObjId

# Models
from pydantic import Field


class ReviewModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a review in the database"""

    # Identification
    id: Optional[ObjId] = Field(None, alias="_id")
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

    @dataclasses.dataclass
    class Settings:
        """Name in database"""
        name = "reviews"


class ReviewView(View):  # pylint: disable=too-many-ancestors
    """View of the Review Model"""

    # Identification
    id: Optional[ObjId] = Field(None, alias="_id")
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
