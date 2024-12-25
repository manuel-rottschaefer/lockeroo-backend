"""User Models."""
# Types
import dataclasses

# Basics
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID
from pydantic import Field

# Beanie
from beanie import Document
from beanie import PydanticObjectId as ObjId
from beanie import View
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
    fief_id: UUID
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

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "users"


class UserSummary(View):
    """Summary of a user entity."""
    # Identification
    id: ObjId = Field(alias="_id")
    first_name: str
    total_sessions: int = 0
    total_session_duration: int = 0
