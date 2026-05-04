"""
Security helpers for v3.2.1 minimal administrative authentication.

Phase 2 implements:
- password hash verification (no plaintext comparison)
- signed access token creation
- token decode/validation (including expiration)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from passlib.context import CryptContext

_PWD_CONTEXT = CryptContext(
    schemes=["bcrypt", "pbkdf2_sha256"],
    deprecated="auto",
)

_JWT_ALG = "HS256"


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    Verify that the submitted plaintext password matches the stored hash.

    Returns False for invalid inputs; never raises for typical verification failures.
    """
    if not plain_password or not password_hash:
        return False
    try:
        return bool(_PWD_CONTEXT.verify(plain_password, password_hash))
    except Exception:
        # Invalid hash formats or unsupported schemes should fail closed.
        return False


def create_access_token(
    subject: str,
    *,
    username: str,
    role: str,
    principal_id: str = "admin",
    secret: str,
    expires_minutes: int,
    now: datetime | None = None,
) -> str:
    """
    Create a signed access token for an authenticated v3 administrator session.

    JWT claim contract (do not conflate ``sub`` with the human login identity):

    - **sub** — Fixed JWT subject / route category for compatibility with existing guards
      (callers pass ``\"admin\"``; it is *not* the secondary principal id).
    - **principal_id** — Stable authenticated principal (matches ``AuthUser.id``), e.g.
      ``\"admin\"`` (primary) or ``\"jairo\"`` (temporary env user).
    - **username** — Visible login name from env (primary) or fixed ``\"Jairo\"``.
    - **role** — Role claim (v3 minimal auth: shared ``administrator`` for both principals).
    - **jti** — Unique token id so successive issuances are not byte-identical in the same second.
    - **iat**, **exp** — UTC epoch seconds.

    Callers that decode tokens must treat a missing **principal_id** as the primary principal
    (see ``get_current_admin``) for backward compatibility with legacy tokens.
    """
    if not secret or not isinstance(secret, str):
        raise ValueError("auth token secret is missing")
    if expires_minutes < 1:
        raise ValueError("expires_minutes must be >= 1")
    if not (principal_id or "").strip():
        raise ValueError("principal_id must be non-empty")

    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    iat = int(now_dt.timestamp())
    exp_dt = now_dt + timedelta(minutes=expires_minutes)
    exp = int(exp_dt.timestamp())

    payload: dict[str, Any] = {
        "sub": subject,
        "principal_id": principal_id,
        "username": username,
        "role": role,
        "jti": str(uuid4()),
        "iat": iat,
        "exp": exp,
    }
    token = jwt.encode(payload, secret, algorithm=_JWT_ALG)
    if not isinstance(token, str):
        # PyJWT may return bytes in older versions; normalize.
        token = token.decode("utf-8")
    return token


def decode_access_token(token: str, *, secret: str) -> dict[str, Any]:
    """
    Decode and validate a previously issued access token.

    ``principal_id`` is not a required JWT claim: legacy tokens omit it; callers
    (e.g. ``get_current_admin``) supply the primary-principal default.

    Raises jwt exceptions for invalid/expired tokens; callers should map to
    AuthErrorResponse contract.
    """
    if not token or not secret:
        raise jwt.InvalidTokenError("missing token or secret")
    decoded = jwt.decode(
        token,
        secret,
        algorithms=[_JWT_ALG],
        options={
            "require": ["exp", "iat", "sub"],
        },
    )
    if not isinstance(decoded, dict):
        raise jwt.InvalidTokenError("invalid token payload")
    return decoded
