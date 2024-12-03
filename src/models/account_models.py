"""User Models."""
# Types
import dataclasses
# Basics
from datetime import datetime
from enum import Enum
from typing import Optional

# Beanie
from beanie import Document
from beanie import PydanticObjectId as ObjId
from beanie import View
from fastapi_users_db_beanie import BeanieBaseUser
# Types
from pydantic import Field


class AuthMethod(str, Enum):
    """Types of supported auth methods"""

    EMAIL = "email"
    GOOGLE = "google"
    APPLE = "apple"


class UserModel(BeanieBaseUser, Document):  # pylint: disable=too-many-ancestors
    """Representation of a user in the database"""

    # Identification
    id: ObjId = Field(alias="_id")
    first_name: str
    last_name: str
    email: Optional[str]

    # Authentication
    hashed_password: Optional[str] = None

    # User Properties
    active_auth_method: AuthMethod = AuthMethod.EMAIL
    has_active_session: bool = False

    # User statistics
    signedUpTS: datetime
    lastLoginTS: Optional[datetime] = None
    totalSessions: int = 0
    totalSessionDuration: int = 0

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


class UserCreate(BeanieBaseUser):
    """View after creation of a user."""

    firstName: str
    lastName: str
    email: Optional[str]
    password: str
    activeAuthMethod: AuthMethod = AuthMethod.EMAIL


class UserUpdate(BeanieBaseUser):
    """View after update of a user."""

    firstName: Optional[str] = None
    lastName: Optional[str] = None


# async def get_user_db():
#    yield BeanieUserDatabase(UserModel)
