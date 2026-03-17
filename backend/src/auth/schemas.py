from __future__ import annotations

"""
Pydantic schemas for auth-related requests and responses (v3.2.1).

Phase 1 defines contracts only; behavior is implemented in later phases.
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request body for the single administrator."""

    username: str = Field(..., description="Administrator username.")
    password: str = Field(..., description="Administrator password (plaintext, not stored).")


class AuthUser(BaseModel):
    """Minimal authenticated admin principal returned to the frontend."""

    id: str = Field(..., description="Stable identifier for the administrator (e.g. 'admin').")
    username: str = Field(..., description="Administrator username.")
    role: str = Field(default="administrator", description="Fixed role name for v3.2.1.")


class LoginResponse(BaseModel):
    """Login success response returned on valid credentials."""

    access_token: str = Field(..., description="Signed bearer token for authenticated access.")
    token_type: str = Field(default="bearer", description="Token type, e.g. 'bearer'.")
    expires_in: int = Field(
        ...,
        description="Access token lifetime in seconds (derived from AUTH_TOKEN_EXPIRES_MINUTES).",
    )
    refresh_token: str | None = Field(
        default=None,
        description="Opaque refresh token for session renewal. Present when refresh is enabled.",
    )
    refresh_expires_in: int | None = Field(
        default=None,
        description="Refresh token lifetime in seconds (derived from AUTH_REFRESH_TOKEN_EXPIRES_MINUTES).",
    )
    user: AuthUser = Field(..., description="Authenticated admin principal.")


class CurrentUserResponse(AuthUser):
    """Response body for optional `/auth/me` endpoint."""

    pass


class AuthError(BaseModel):
    """Machine-readable error payload for auth failures."""

    code: str = Field(..., description="Stable error code, e.g. INVALID_CREDENTIALS or UNAUTHORIZED.")
    message: str = Field(..., description="Human-readable error message.")


class AuthErrorResponse(BaseModel):
    """Standardized unauthorized/invalid-credentials error envelope."""

    error: AuthError


class RefreshRequest(BaseModel):
    """Request body for POST /auth/refresh and POST /auth/logout."""

    refresh_token: str = Field(..., description="Opaque refresh token issued by the login/refresh endpoints.")

