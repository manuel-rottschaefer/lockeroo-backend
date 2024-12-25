"""This module provides the Models for review management."""
# Types
from dataclasses import dataclass
from typing import Optional
# Basics
from datetime import datetime

# Beanie
from beanie import Document, Link
from beanie import PydanticObjectId as ObjId
from beanie import View, Insert, after_event
from pydantic import Field

# Models
from src.models.session_models import SessionModel


class ReviewModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a review in the database"""

    # Identification
    id: ObjId = Field(None, alias="_id")
    assigned_session: Link[SessionModel] = Field(
        description="The session to which the review refers to.")

    submitted_at: Optional[datetime] = Field(
        None, description="Timestamp of review submission."
    )

    experience_rating: int = Field(
        ge=1, le=5, description="Rating of the overall experience."
    )
    cleanliness_rating: int = Field(
        ge=1, le=5, description="Rating of the cleanliness of the locker."
    )
    details: str = Field(
        description="Written feedback on the session. Should not be made public."
    )

    @ after_event(Insert)
    def handle_review_creation(self):
        self.submitted_at = datetime.now()

    @ dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "reviews"

    @ dataclass
    class Config:  # pylint: disable=missing-class-docstring
        json_schema_extra = {
            "assigned_session": "60d5ec49f1d2b2a5d8f8b8b8",
            "experience_rating": 5,
            "cleanliness_rating": 4,
            "details": "Great experience!"
        }


class ReviewView(View):  # pylint: disable=too-many-ancestors
    """View of the Review Model"""
    # Identification
    id: ObjId = Field(None)
    assigned_session: ObjId

    submitted_at: datetime

    experience_rating: int = Field(
        ge=1, le=5, description="Rating of the overall experience"
    )
    cleanliness_rating: int = Field(
        ge=1, le=5, description="Rating of the cleanliness of the locker"
    )
    details: str = Field(
        description="Written feedback on the session. Should not be made public."
    )

    @ dataclass
    class Config:  # pylint: disable=missing-class-docstring
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "assigned_session": "60d5ec49f1d2b2a5d8f8b8b8",
            "submitted_at": "2023-10-10T10:00:00",
            "experience_rating": 5,
            "cleanliness_rating": 4,
            "details": "Great experience!"
        }
