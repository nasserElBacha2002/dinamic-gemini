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
    if sub != "admin" or not isinstance(username, str) or not isinstance(role, str):
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )

    return AuthUser(id="admin", username=username, role=role)

