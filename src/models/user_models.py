"""User Models."""
# Types
from typing import List
from dataclasses import dataclass
# Basics
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
# Beanie
from beanie import Document, View, PydanticObjectId as ObjId
from pydantic import BaseModel, Field, PydanticUserError

# from fastapi_users_db_beanie import BeanieBaseUser


class AuthMethod(str, Enum):
    """Types of supported auth methods"""
    EMAIL = "email"
    GOOGLE = "google"
    APPLE = "apple"


class UserModel(Document):  # pylint: disable=too-many-ancestors
    """Representation of a user in the database"""
    id: ObjId = Field(None, alias="_id")
    fief_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier of user.")
    first_name: Optional[str] = Field(None, description="First name of user.")
    last_name: Optional[str] = Field(None, description="Last name of user.")
    email: Optional[str] = Field(
        None, description="Assigned email address of usr")

    # Authentication
    hashed_password: Optional[str] = Field(
        None, description="Hashed password of user.")

    # User Properties
    active_auth_method: AuthMethod = Field(
        AuthMethod.EMAIL, description="Active authentication method.")
    has_active_session: bool = Field(
        False, description="Whether the user has an active session.")

    # User statistics
    signup_at: datetime = Field(
        datetime.now(), description="Timestamp of user signup.")
    last_login_at: Optional[datetime] = Field(
        None, description="Timestamp of last login.")

    total_session_count: int = Field(0, description="Amount of total sessions")
    total_session_duration: float = Field(
        0, description="Total amount of all sessions in seconds.")

    @dataclass
    class Settings:
        name = "users"

    @dataclass
    class Config:
        json_schema_extra = {
            "fief_id": "12345678-1234-5678-1234-567812345678",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "hashed_password": "hashed_password",
            "active_auth_method": "email",
            "has_active_session": False,
            "signup_at": "2023-10-10T10:00:00",
            "last_login_at": "ADAPT HERE"}


class AuthenticatedUserModel(BaseModel):
    """Authenticated user"""
    id: ObjId = Field(None, alias="_id")
    fief_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier of user.")
    first_name: Optional[str] = Field(None, description="First name of user.")
    last_name: Optional[str] = Field(None, description="Last name of user.")
    email: Optional[str] = Field(
        None, description="Assigned email address of usr")

    # User Properties
    active_auth_method: AuthMethod = Field(
        AuthMethod.EMAIL, description="Active authentication method.")
    has_active_session: bool = Field(
        False, description="Whether the user has an active session.")

    permissions: List = Field([], description="List of user permissions.")

    @dataclass
    class Settings:
        name = "users"

    @dataclass
    class Config:
        json_schema_extra = {
            "fief_id": "12345678-1234-5678-1234-567812345678",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "active_auth_method": "email",
            "has_active_session": False,
        }


class UserSummary(View):
    """Summary of a user entity."""
    # Identification
    id: ObjId = Field(None, alias="_id")
    first_name: str
    last_name: str
    email: Optional[str]

    @dataclass
    class Settings:
        source = UserModel
        is_root = False
        projection = {
            "id": '$fief_id',
            "first_name": '$first_name',
            "last_name": '$last_name',
            "email": '$email'
        }

    @dataclass
    class Config:
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@mail.net"
        }


class UserQuickStats(View):
    """Quick stats of a user entity."""
    # Identification
    id: ObjId = Field(None, alias="_id")
    total_sessions: int = 0
    total_session_duration: int = 0

    @dataclass
    class Settings:
        source = UserModel
        is_root = False
        projection = {
            "id": '$fief_id',
            "total_sessions": '$total_session_count',
            "total_session_duration": '$total_session_duration'
        }

    @dataclass
    class Config:
        json_schema_extra = {
            "id": "60d5ec49f1d2b2a5d8f8b8b8",
            "total_sessions": 5,
            "total_session_duration": 3600
        }


try:
    for model in [UserModel, UserSummary, UserQuickStats]:
        model.model_json_schema()
except PydanticUserError as exc_info:
    assert exc_info.code == 'invalid-for-json-schema'
