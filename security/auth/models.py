"""User and Role models for authentication and authorization."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    """Platform roles with increasing privilege levels."""
    ANALYST = "analyst"
    INVESTIGATOR = "investigator"
    ADMIN = "admin"


# Permission definitions per role
ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ANALYST: {
        "alerts:read",
        "transactions:read",
        "copilot:use",
        "dashboard:view",
        "reports:read",
    },
    Role.INVESTIGATOR: {
        "alerts:read",
        "alerts:update",
        "transactions:read",
        "copilot:use",
        "dashboard:view",
        "reports:read",
        "reports:generate",
        "investigations:create",
        "investigations:update",
    },
    Role.ADMIN: {
        "alerts:read",
        "alerts:update",
        "alerts:delete",
        "transactions:read",
        "copilot:use",
        "dashboard:view",
        "reports:read",
        "reports:generate",
        "investigations:create",
        "investigations:update",
        "users:manage",
        "models:retrain",
        "system:config",
    },
}


class UserBase(BaseModel):
    """Base user model."""
    username: str = Field(min_length=3, max_length=50)
    email: str
    role: Role = Role.ANALYST
    is_active: bool = True


class UserCreate(UserBase):
    """Model for creating a new user."""
    password: str = Field(min_length=8, max_length=128)


class User(UserBase):
    """Stored user model."""
    user_id: str
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # user_id
    username: str
    role: Role
    exp: int
    iat: int
    token_type: str = "access"


class TokenPair(BaseModel):
    """Access and refresh token pair."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
