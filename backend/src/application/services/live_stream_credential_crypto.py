"""Credential helpers for DIN-508 live stream."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from passlib.context import CryptContext

from src.auth.security import verify_password

# pbkdf2_sha256 avoids passlib+bcrypt 5.x backend init failures (72-byte probe during detect_wrap_bug).
_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def mint_stream_username(prefix: str, channel_slug: str) -> str:
    safe_slug = "".join(c for c in channel_slug if c.isalnum())
    return f"{prefix}_{safe_slug[:12]}"


def mint_readable_stream_username(
    prefix: str,
    *,
    inventory_name: str,
    aisle_code: str,
) -> str:
    """DJI-friendly login (e.g. pub_Prueba18-09_P1)."""
    from src.domain.live_stream.channel_identity import (
        canonical_aisle_code_for_channel,
        slugify_path_segment,
    )

    inv = slugify_path_segment(inventory_name)[:24] or "inv"
    aisle = slugify_path_segment(canonical_aisle_code_for_channel(aisle_code))[:12] or "aisle"
    return f"{prefix}_{inv}_{aisle}"[:80]


def mint_public_view_username(*, grant_id: str) -> str:
    """MediaMTX login unique per grant (UQ_aisle_live_view_grants_view_user)."""
    compact = "".join(c for c in grant_id if c.isalnum())
    return f"pubview_{compact[:32]}"


def hash_public_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_public_token() -> str:
    return secrets.token_urlsafe(32)


def derive_channel_password(*, server_secret: str, mediamtx_path: str, purpose: str) -> str:
    """Deterministic per-channel secret derivable only server-side (no plaintext at rest)."""
    key = (server_secret or "").encode("utf-8")
    if not key:
        raise ValueError("server_secret required for live stream credentials")
    msg = f"din508:{purpose}:{mediamtx_path}".encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    # Short hex — easier to type in DJI Fly; still server-derived per path.
    return digest.hex()[:12]


def derive_public_grant_password(*, server_secret: str, grant_id: str) -> str:
    key = (server_secret or "").encode("utf-8")
    msg = f"din508:public:{grant_id}".encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    raw = base64.urlsafe_b64encode(digest).decode("ascii")
    return raw.replace("%", "")[:40]


def passwords_equal(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def hash_live_stream_secret(plain: str) -> str:
    """Persisted verifier for optional hash path (primary auth uses derived plaintext via passwords_equal)."""
    return _PWD_CONTEXT.hash(plain)


def verify_live_stream_secret(plain: str, stored_hash: str) -> bool:
    return verify_password(plain, stored_hash)