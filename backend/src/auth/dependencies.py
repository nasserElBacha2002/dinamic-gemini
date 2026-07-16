"""
FastAPI dependencies for v3.2.1 authentication.

Phase 2 implements current-admin resolution from a bearer token. This dependency
is intended to be reused in Phase 3 when protecting the v3 route surface.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, Request, status

from src.application.services.observability_access import (
    ObservabilityAuthError,
    principal_has_capability,
    validate_principal_tenant_binding,
)
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
    authenticated admin principal. Non-platform principals without ``client_id``
    are rejected (fail closed).
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
    # Legacy access tokens issued before ``principal_id`` existed: treat as the primary
    # principal (``AuthUser.id`` == "admin"). New tokens always include ``principal_id``.
    raw_pid = payload.get("principal_id", "admin")
    principal_id = raw_pid if isinstance(raw_pid, str) and raw_pid.strip() else "admin"
    if sub != "admin" or not isinstance(username, str) or not isinstance(role, str):
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )
    raw_client = payload.get("client_id")
    client_id = (
        raw_client.strip()
        if isinstance(raw_client, str) and raw_client.strip()
        else None
    )

    user = AuthUser(id=principal_id, username=username, role=role, client_id=client_id)
    try:
        validate_principal_tenant_binding(user)
    except ObservabilityAuthError as exc:
        raise AuthHttpError(
            status_code=status.HTTP_403_FORBIDDEN,
            error=AuthError(code=exc.code, message=exc.message),
        ) from exc
    return user


def require_observability_capability(capability: str):
    """FastAPI dependency factory: require an Observability capability (403 if missing)."""

    def _dep(user: AuthUser = Depends(get_current_admin)) -> AuthUser:
        if not principal_has_capability(user, capability):
            raise AuthHttpError(
                status_code=status.HTTP_403_FORBIDDEN,
                error=AuthError(
                    code="FORBIDDEN_CAPABILITY",
                    message=f"Missing capability: {capability}",
                ),
            )
        return user

    return _dep


def require_ai_config_inspection_user(
    admin: AuthUser = Depends(get_current_admin),
) -> AuthUser:
    """
    Gate for AI configuration inspection (GET ``/api/v3/admin/ai-config`` and related routes).

    Policy (both required):
    1. Caller passed ``get_current_admin`` — valid v3 administrator JWT (Bearer).
    2. ``AuthUser.id`` is exactly ``\"admin\"`` — the primary env administrator principal only.

    Secondary env principals (e.g. temporary ``Jairo``, ``AuthUser.id == \"jairo\"``) use the same
    ``role`` for general v3 routes but receive **403** on this inspection-only surface.
    """
    if admin.id != "admin":
        raise AuthHttpError(
            status_code=status.HTTP_403_FORBIDDEN,
            error=AuthError(
                code="FORBIDDEN",
                message="AI configuration inspection is restricted to the primary administrator principal.",
            ),
        )
    return admin


# Backward-compatible name for imports/tests that still reference the old symbol.
require_username_admin_for_ai_config = require_ai_config_inspection_user
