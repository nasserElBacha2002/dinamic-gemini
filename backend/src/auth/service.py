"""
Auth service layer for v3.2.1 minimal administrative authentication.

Phase 2 implements:
- admin credential validation (single configured admin)
- login response building (token + principal)
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import status

from src.auth.config import AuthSettings, get_auth_settings
from src.auth.errors import AuthHttpError
from src.auth.schemas import AuthError, AuthUser, LoginRequest, LoginResponse
from src.auth.security import create_access_token, verify_password


@dataclass(frozen=True)
class AuthContext:
    """Lightweight container for auth settings and clocks/services."""

    settings: AuthSettings


def get_auth_context() -> AuthContext:
    """Factory used by dependencies to build an AuthContext."""

    return AuthContext(settings=get_auth_settings())


def authenticate_admin(command: LoginRequest, context: AuthContext) -> Optional[AuthUser]:
    """
    Validate administrator credentials and build the AuthUser principal.

    Returns AuthUser on success; None on invalid credentials.
    Does not log credentials and does not distinguish which field failed.
    """
    s = context.settings
    if not s.admin_username or not s.admin_password_hash:
        # Misconfiguration; treat as invalid credentials at this layer.
        return None
    if (command.username or "").strip() != s.admin_username:
        return None
    if not verify_password(command.password, s.admin_password_hash):
        return None
    return AuthUser(id="admin", username=s.admin_username, role="administrator")


def build_login_response(user: AuthUser, context: AuthContext) -> LoginResponse:
    """
    Build a LoginResponse for a successfully authenticated admin.

    Creates a signed bearer token and returns the stable LoginResponse DTO.
    """
    s = context.settings
    if not (s.token_secret or "").strip():
        raise AuthHttpError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error=AuthError(code="SERVER_ERROR", message="Auth is misconfigured."),
        )
    token = create_access_token(
        "admin",
        username=user.username,
        role=user.role,
        secret=s.token_secret,
        expires_minutes=s.token_expires_minutes,
    )
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=s.token_expires_minutes * 60,
        user=user,
    )

