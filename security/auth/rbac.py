"""Role-based access control (RBAC) decorators and utilities."""

from __future__ import annotations

from functools import wraps
from typing import Callable

from fastapi import HTTPException, status

from .models import ROLE_PERMISSIONS, Role, TokenPayload


def has_permission(role: Role, permission: str) -> bool:
    """Check if a role has a specific permission.

    Args:
        role: The user's role.
        permission: Permission string (e.g., "alerts:update").

    Returns:
        True if the role includes this permission.
    """
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_permission(permission: str) -> Callable:
    """FastAPI dependency factory: require a specific permission.

    Usage:
        @router.get("/admin/users")
        async def list_users(user: TokenPayload = Depends(require_permission("users:manage"))):
            ...

    Args:
        permission: Required permission string.

    Returns:
        A FastAPI dependency function.
    """
    from fastapi import Depends, Request

    async def _check_permission(request: Request) -> TokenPayload:
        user: TokenPayload = request.state.user
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required. Your role '{user.role.value}' does not have it.",
            )
        return user

    return Depends(_check_permission)


def require_role(*roles: Role) -> Callable:
    """FastAPI dependency factory: require one of the specified roles.

    Usage:
        @router.post("/models/retrain")
        async def retrain(user: TokenPayload = Depends(require_role(Role.ADMIN))):
            ...

    Args:
        roles: Allowed roles.

    Returns:
        A FastAPI dependency function.
    """
    from fastapi import Depends, Request

    async def _check_role(request: Request) -> TokenPayload:
        user: TokenPayload = request.state.user
        if user.role not in roles:
            allowed = ", ".join(r.value for r in roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Roles [{allowed}] required. Your role is '{user.role.value}'.",
            )
        return user

    return Depends(_check_role)
