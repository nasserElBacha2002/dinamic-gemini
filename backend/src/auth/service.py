"""
Auth service layer for v3.2.1 minimal administrative authentication.

Provisioning policy (temporary second user):
- The primary administrator (``ADMIN_USERNAME`` + ``ADMIN_PASSWORD_HASH``) must always be
  configured for any login to succeed, including the optional env user **Jairo**.
- ``AUTH_JAIRO_PASSWORD_HASH`` is optional; when absent/empty, Jairo is disabled.
- This is not multi-user product support: no registration, no DB users, no RBAC.

Phase 2 implements:
- admin credential validation (primary env admin + optional temporary \"Jairo\" operator)
- login response building (token + principal)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Optional
from uuid import uuid4

from fastapi import status

from src.auth.config import AuthSettings, get_auth_settings
from src.auth.errors import AuthHttpError
from src.auth.schemas import AuthError, AuthUser, LoginRequest, LoginResponse
from src.auth.security import create_access_token, verify_password

# Temporary second operator (env-provisioned hash only; no registration flow).
_JAIRO_LOGIN_USERNAME = "Jairo"
_JAIRO_PRINCIPAL_ID = "jairo"


def _primary_admin_credentials_configured(s: AuthSettings) -> bool:
    """True when primary admin username and password hash are both non-empty (trimmed)."""
    return bool(s.admin_username and s.admin_password_hash)


@dataclass(frozen=True)
class AuthContext:
    """Lightweight container for auth settings and clocks/services."""

    settings: AuthSettings


def get_auth_context() -> AuthContext:
    """Factory used by dependencies to build an AuthContext."""

    return AuthContext(settings=get_auth_settings())


@dataclass
class RefreshTokenRecord:
    """In-memory refresh token record per authenticated principal (v3.2.3.E6).

    This is intentionally simple and process-local; it can be replaced by a
    repository-backed implementation in a later phase without changing the
    public auth contracts.
    """

    id: str
    user_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    replaced_by_token_id: str | None = None


_REFRESH_TOKENS: dict[str, RefreshTokenRecord] = {}
_REFRESH_TOKENS_BY_HASH: dict[str, str] = {}


def _now_utc() -> datetime:
    dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _issue_refresh_token(user_id: str, context: AuthContext) -> tuple[str, RefreshTokenRecord]:
    """Create and persist a new refresh token for this principal (user_id = AuthUser.id)."""
    raw = uuid4().hex + uuid4().hex
    token_hash = _hash_token(raw)
    now = _now_utc()
    expires_at = now + timedelta(minutes=context.settings.refresh_token_expires_minutes)
    rec = RefreshTokenRecord(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=now,
        expires_at=expires_at,
    )
    _REFRESH_TOKENS[rec.id] = rec
    _REFRESH_TOKENS_BY_HASH[token_hash] = rec.id
    return raw, rec


def _find_refresh_record(refresh_token: str) -> RefreshTokenRecord | None:
    if not refresh_token:
        return None
    token_hash = _hash_token(refresh_token)
    rec_id = _REFRESH_TOKENS_BY_HASH.get(token_hash)
    if not rec_id:
        return None
    return _REFRESH_TOKENS.get(rec_id)


def _revoke_token_record(
    rec: RefreshTokenRecord, *, replaced_by: RefreshTokenRecord | None = None
) -> None:
    now = _now_utc()
    rec.revoked_at = now
    if replaced_by is not None:
        rec.replaced_by_token_id = replaced_by.id


def _revoke_all_for_user(user_id: str) -> None:
    for rec in _REFRESH_TOKENS.values():
        if rec.user_id == user_id and rec.revoked_at is None:
            rec.revoked_at = _now_utc()


def authenticate_admin(command: LoginRequest, context: AuthContext) -> Optional[AuthUser]:
    """
    Validate administrator credentials and build the AuthUser principal.

    Returns AuthUser on success; None on invalid credentials.
    Does not log credentials and does not distinguish which field failed.
    """
    s = context.settings
    submitted_user = (command.username or "").strip()
    submitted_pw = command.password or ""

    if _primary_admin_credentials_configured(s):
        if submitted_user == s.admin_username and verify_password(
            submitted_pw, s.admin_password_hash
        ):
            return AuthUser(
                id="admin",
                username=s.admin_username,
                role="administrator",
                client_id=(s.admin_client_id or "").strip() or None,
            )

    # Jairo is an add-on only: requires a fully configured primary admin (Policy A).
    if (
        _primary_admin_credentials_configured(s)
        and (s.jairo_password_hash or "").strip()
        and submitted_user == _JAIRO_LOGIN_USERNAME
        and verify_password(submitted_pw, s.jairo_password_hash)
    ):
        return AuthUser(
            id=_JAIRO_PRINCIPAL_ID,
            username=_JAIRO_LOGIN_USERNAME,
            role="administrator",
            client_id=(s.jairo_client_id or "").strip() or None,
        )

    return None


def _auth_user_from_principal_id(principal_id: str, context: AuthContext) -> AuthUser:
    """Rebuild AuthUser for refresh/logout flows from stored principal id."""
    s = context.settings
    if principal_id == _JAIRO_PRINCIPAL_ID:
        return AuthUser(
            id=_JAIRO_PRINCIPAL_ID,
            username=_JAIRO_LOGIN_USERNAME,
            role="administrator",
            client_id=(s.jairo_client_id or "").strip() or None,
        )
    return AuthUser(
        id="admin",
        username=s.admin_username,
        role="administrator",
        client_id=(s.admin_client_id or "").strip() or None,
    )


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
    access_token = create_access_token(
        "admin",
        username=user.username,
        role=user.role,
        principal_id=user.id,
        client_id=user.client_id,
        secret=s.token_secret,
        expires_minutes=s.token_expires_minutes,
    )
    refresh_token, _ = _issue_refresh_token(user.id, context)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=s.token_expires_minutes * 60,
        refresh_token=refresh_token,
        refresh_expires_in=s.refresh_token_expires_minutes * 60,
        user=user,
    )


def refresh_session(refresh_token: str, context: AuthContext) -> LoginResponse:
    """
    Validate and rotate a refresh token, returning a new LoginResponse payload.

    Old token becomes invalid; new refresh token is the only valid one for the session.
    Basic reuse protection: if a revoked/replaced token is seen again, revoke all tokens
    for the admin and fail the refresh.
    """
    s = context.settings
    if not (s.token_secret or "").strip():
        raise AuthHttpError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error=AuthError(code="SERVER_ERROR", message="Auth is misconfigured."),
        )
    rec = _find_refresh_record(refresh_token)
    now = _now_utc()
    if rec is None or rec.expires_at <= now:
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )
    if rec.revoked_at is not None or rec.replaced_by_token_id is not None:
        # Token reuse or already rotated; revoke entire chain for safety.
        _revoke_all_for_user(rec.user_id)
        raise AuthHttpError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error=AuthError(code="UNAUTHORIZED", message="Authentication required."),
        )

    # Rotate: revoke old record, issue new one.
    new_refresh_token, new_rec = _issue_refresh_token(rec.user_id, context)
    _revoke_token_record(rec, replaced_by=new_rec)

    user = _auth_user_from_principal_id(rec.user_id, context)
    access_token = create_access_token(
        "admin",
        username=user.username,
        role=user.role,
        principal_id=user.id,
        secret=s.token_secret,
        expires_minutes=s.token_expires_minutes,
    )
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=s.token_expires_minutes * 60,
        refresh_token=new_refresh_token,
        refresh_expires_in=s.refresh_token_expires_minutes * 60,
        user=user,
    )


def logout_session(refresh_token: str | None, context: AuthContext) -> None:
    """
    Revoke the supplied refresh token if present; no-op when token is missing/unknown.
    """
    if not refresh_token:
        return
    rec = _find_refresh_record(refresh_token)
    if rec is None:
        return
    _revoke_token_record(rec)
