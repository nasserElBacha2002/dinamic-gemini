"""
Auth routes for v3.2.1 minimal administrative authentication.

Phase 2 implements working /auth/login and /auth/me endpoints using the stable
contracts introduced in Phase 1.
"""

from fastapi import APIRouter, Depends, status

from src.api.constants.route_paths import API_AUTH_ROUTER_PREFIX
from src.auth.dependencies import get_auth_context_dep, get_current_admin
from src.auth.errors import AuthHttpError
from src.auth.schemas import (
    AuthError,
    AuthErrorResponse,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
)
from src.auth.service import (
    AuthContext,
    authenticate_admin,
    build_login_response,
    logout_session,
    refresh_session,
)

router = APIRouter(prefix=API_AUTH_ROUTER_PREFIX, tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": AuthErrorResponse},
    },
)
async def login(
    body: LoginRequest,
    context: AuthContext = Depends(get_auth_context_dep),
) -> LoginResponse:
    """
    Administrator login endpoint.

    Valid credentials return a signed access token and admin principal.
    Invalid credentials return a stable auth error contract without leaking
    whether username or password failed.
    """
    user = authenticate_admin(body, context)
    if user is None:
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="INVALID_CREDENTIALS", message="Invalid credentials."),
        )
    return build_login_response(user, context)


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": AuthErrorResponse},
    },
)
async def get_me(current: CurrentUserResponse = Depends(get_current_admin)) -> CurrentUserResponse:
    """
    Optional current-user endpoint.
    """
    return current


@router.post(
    "/refresh",
    response_model=LoginResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": AuthErrorResponse},
    },
)
async def refresh_tokens(
    body: RefreshRequest,
    context: AuthContext = Depends(get_auth_context_dep),
) -> LoginResponse:
    """
    Refresh endpoint for admin session (v3.2.3.E6).

    Accepts a refresh token, validates and rotates it, and returns a new pair of
    access + refresh tokens together with the admin principal.
    """
    try:
        return refresh_session(body.refresh_token, context)
    except AuthHttpError:
        # Propagate standardized auth errors.
        raise


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": AuthErrorResponse},
    },
)
async def logout(
    body: RefreshRequest,
    _: CurrentUserResponse = Depends(get_current_admin),
    context: AuthContext = Depends(get_auth_context_dep),
) -> None:
    """
    Logout endpoint for admin session (v3.2.3.E6).

    Revokes the supplied refresh token; subsequent use of that token will fail.
    Requires a valid access token (same as other protected endpoints).
    """
    logout_session(body.refresh_token, context)
