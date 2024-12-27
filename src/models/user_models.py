"""User Models."""
# Types
from dataclasses import dataclass
# Basics
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

# Beanie
from beanie import Document
from beanie import PydanticObjectId as ObjId
from beanie import View
from pydantic import Field, PydanticUserError

# from fastapi_users_db_beanie import BeanieBaseUser


class AuthMethod(str, Enum):
    """Types of supported auth methods"""

    EMAIL = "email"
    GOOGLE = "google"
    APPLE = "apple"


class UserModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a user in the database"""

    # Identification
    id: ObjId = Field(None, alias="_id")
    fief_id: UUID = Field(None, description="Unique identifier of user.")
    first_name: Optional[str] = Field(None, description="First name of user.")
    last_name: Optional[str] = Field(None, description="Last name of user.")
    email: Optional[str] = Field(
        None, description="Assigned email address of usr")

    # Authentication
    hashed_password: Optional[str] = None

    # User Properties
    active_auth_method: AuthMethod = AuthMethod.EMAIL
    has_active_session: bool = False

    # User statistics
    signup_at: datetime = Field(
        datetime.now(), description="Timestamp of user signup.")
    last_login_at: Optional[datetime] = None

    total_session_count: int = Field(0, description="Amount of total sessions")
    total_session_duration: float = Field(
        0, description="Total amount of all sessions in seconds.")

    @ dataclass
    class Settings:
        name = "users"

    @ dataclass
    class Config:
        json_schema_extra = {
            "fief_id": "12345678-1234-5678-1234-567812345678",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "hashed_password": "hashed_password",
            "active_auth_method": "email",
            "has_active_session": False,
            "signup_at": "2023-10-10T10:00:00"
        }


try:
    UserModel.model_json_schema()
except PydanticUserError as exc_info:
    assert exc_info.code == 'invalid-for-json-schema'


class UserSummary(View):
    """Summary of a user entity."""
    # Identification
    id: str = Field(description="Unique identifier of the user.")
    first_name: str
    total_sessions: int = 0
    total_session_duration: int = 0

    @ dataclass
    class Settings:
        source = UserModel

    @ dataclass
    class Config:
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "first_name": "John",
            "total_sessions": 5,
            "total_session_duration": 3600
        }
