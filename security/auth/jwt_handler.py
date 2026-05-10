"""JWT token creation, validation, and refresh."""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

import jwt
import structlog

from .models import Role, TokenPair, TokenPayload

logger = structlog.get_logger(__name__)

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fraud-platform-jwt-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRY_SECONDS = int(os.getenv("ACCESS_TOKEN_EXPIRY", "3600"))  # 1 hour
REFRESH_TOKEN_EXPIRY_SECONDS = int(os.getenv("REFRESH_TOKEN_EXPIRY", "86400"))  # 24 hours


def create_access_token(user_id: str, username: str, role: Role) -> str:
    """Create a signed JWT access token.

    Args:
        user_id: Unique user identifier.
        username: Human-readable username.
        role: User's role for RBAC.

    Returns:
        Encoded JWT string.
    """
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "role": role.value,
        "exp": now + ACCESS_TOKEN_EXPIRY_SECONDS,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "token_type": "access",
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug("access_token_created", user_id=user_id, expires_in=ACCESS_TOKEN_EXPIRY_SECONDS)
    return token


def create_refresh_token(user_id: str, username: str, role: Role) -> str:
    """Create a signed JWT refresh token.

    Args:
        user_id: Unique user identifier.
        username: Human-readable username.
        role: User's role.

    Returns:
        Encoded JWT string.
    """
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "role": role.value,
        "exp": now + REFRESH_TOKEN_EXPIRY_SECONDS,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "token_type": "refresh",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_token_pair(user_id: str, username: str, role: Role) -> TokenPair:
    """Create both access and refresh tokens.

    Args:
        user_id: Unique user identifier.
        username: Human-readable username.
        role: User's role.

    Returns:
        TokenPair with access and refresh tokens.
    """
    return TokenPair(
        access_token=create_access_token(user_id, username, role),
        refresh_token=create_refresh_token(user_id, username, role),
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRY_SECONDS,
    )


def validate_token(token: str, expected_type: str = "access") -> TokenPayload:
    """Validate and decode a JWT token.

    Args:
        token: The JWT string to validate.
        expected_type: Expected token_type claim ("access" or "refresh").

    Returns:
        Decoded TokenPayload.

    Raises:
        jwt.ExpiredSignatureError: Token has expired.
        jwt.InvalidTokenError: Token is invalid.
        ValueError: Token type mismatch.
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    if payload.get("token_type") != expected_type:
        raise ValueError(f"Expected {expected_type} token, got {payload.get('token_type')}")

    return TokenPayload(
        sub=payload["sub"],
        username=payload["username"],
        role=Role(payload["role"]),
        exp=payload["exp"],
        iat=payload["iat"],
        token_type=payload["token_type"],
    )


def refresh_access_token(refresh_token: str) -> TokenPair:
    """Generate a new token pair using a valid refresh token.

    Args:
        refresh_token: Valid refresh JWT.

    Returns:
        New TokenPair.

    Raises:
        jwt.ExpiredSignatureError: Refresh token expired.
        jwt.InvalidTokenError: Invalid refresh token.
    """
    payload = validate_token(refresh_token, expected_type="refresh")
    logger.info("token_refreshed", user_id=payload.sub)
    return create_token_pair(payload.sub, payload.username, payload.role)
