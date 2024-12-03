"""This module provides the Models for account management."""
# Types
import dataclasses

# Basics
from datetime import datetime
from enum import Enum
from typing import Optional

# Beanie
from beanie import Document, View
from beanie import PydanticObjectId as ObjId
from fastapi_users_db_beanie import BeanieBaseUser

# Types
from pydantic import Field


class AuthMethod(str, Enum):
    """Types of supported auth methods"""

    EMAIL = "email"
    GOOGLE = "google"
    APPLE = "apple"


class AccountModel(BeanieBaseUser, Document):  # pylint: disable=too-many-ancestors
    """Representation of a user in the database"""

    # Identification
    id: ObjId = Field(alias="_id")
    first_name: str
    last_name: str
    email: Optional[str]

    # Authentication
    hashed_password: Optional[str] = None

    # Properties
    active_auth_method: AuthMethod = AuthMethod.EMAIL
    has_active_session: bool = False

    # statistics
    signedUpTS: datetime
    lastLoginTS: Optional[datetime] = None
    totalSessions: int = 0
    totalSessionDuration: int = 0

    @dataclasses.dataclass
    class Settings:  # pylint: disable=missing-class-docstring
        name = "accounts"


class AccountSummary(View):
    """Summary of an account."""
    # Identification
    id: ObjId = Field(alias="_id")
    first_name: str
    total_sessions: int = 0
    total_session_duration: int = 0
