"""FastAPI authentication middleware."""

from __future__ import annotations

import time
from typing import Optional

import jwt
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .jwt_handler import validate_token
from .models import TokenPayload

logger = structlog.get_logger(__name__)

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware for FastAPI.

    Validates the Authorization header on every request (except public paths),
    decodes the JWT, and attaches the user payload to request.state.user.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Skip auth for public paths
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # OPTIONS requests (CORS preflight) don't need auth
        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header: Optional[str] = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return Response(
                content='{"detail":"Missing or invalid Authorization header"}',
                status_code=401,
                media_type="application/json",
            )

        token = auth_header[7:]  # Strip "Bearer "

        try:
            payload: TokenPayload = validate_token(token, expected_type="access")
            request.state.user = payload
        except jwt.ExpiredSignatureError:
            logger.warning("token_expired", path=request.url.path)
            return Response(
                content='{"detail":"Token expired"}',
                status_code=401,
                media_type="application/json",
            )
        except (jwt.InvalidTokenError, ValueError) as exc:
            logger.warning("invalid_token", path=request.url.path, error=str(exc))
            return Response(
                content='{"detail":"Invalid token"}',
                status_code=401,
                media_type="application/json",
            )

        response = await call_next(request)
        return response
