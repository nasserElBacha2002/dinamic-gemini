"""
FastAPI dependencies for v3.2.1 authentication.

Phase 2 implements current-admin resolution from a bearer token. This dependency
is intended to be reused in Phase 3 when protecting the v3 route surface.
"""

from __future__ import annotations

from fastapi import Depends, Request, status

import jwt
from src.auth.errors import AuthHttpError
from src.auth.schemas import AuthError, AuthUser
from src.auth.security import decode_access_token
from src.auth.service import AuthContext, get_auth_context


def get_auth_context_dep() -> AuthContext:
    """Dependency that provides an AuthContext for auth routes."""

    return get_auth_context()


def get_current_admin(
    request: Request,
    context: AuthContext = Depends(get_auth_context_dep),
) -> AuthUser:
    """
    Resolve the current authenticated admin from the request.

    Extracts Authorization: Bearer <token>, validates the token, and returns the
    authenticated admin principal.
    """
    auth = (request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )
    token = auth.split(" ", 1)[1].strip()
    if not token:
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )

    settings = context.settings
    if not settings.token_secret:
        # Misconfiguration; fail closed.
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )

    try:
        payload = decode_access_token(token, secret=settings.token_secret)
    except jwt.ExpiredSignatureError:
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )
    except jwt.InvalidTokenError:
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )

    username = payload.get("username")
    role = payload.get("role")
    sub = payload.get("sub")
    raw_pid = payload.get("principal_id", "admin")
    principal_id = raw_pid if isinstance(raw_pid, str) and raw_pid.strip() else "admin"
    if sub != "admin" or not isinstance(username, str) or not isinstance(role, str):
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )

    return AuthUser(id=principal_id, username=username, role=role)


def require_ai_config_inspection_user(
    admin: AuthUser = Depends(get_current_admin),
) -> AuthUser:
    """
    Gate for AI configuration inspection (GET ``/api/v3/admin/ai-config`` and related routes).

    Policy (both required):
    1. Caller passed ``get_current_admin`` — valid admin JWT (any v3 admin username allowed by auth).
    2. ``AuthUser.username`` is exactly the literal ``\"admin\"`` — the operational inspection principal.

    Other authenticated principals (e.g. temporary env user ``Jairo``) remain valid for the rest
    of v3 but receive **403** here so the inspection UI and lazy prompt endpoints stay tied to the
    fixed operational username.
    """
    if admin.username != "admin":
        raise AuthHttpError(
            status_code=status.HTTP_403_FORBIDDEN,
            error=AuthError(
                code="FORBIDDEN",
                message="AI configuration inspection is restricted to the admin username.",
            ),
        )
    return admin


# Backward-compatible name for imports/tests that still reference the old symbol.
require_username_admin_for_ai_config = require_ai_config_inspection_user
