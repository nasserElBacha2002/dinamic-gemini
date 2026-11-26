"""Live stream credential hashing (passlib backend compatibility)."""

from __future__ import annotations

from src.application.services.live_stream_credential_crypto import (
    hash_live_stream_secret,
    verify_live_stream_secret,
)


def test_hash_and_verify_roundtrip() -> None:
    plain = "short-derived-style-secret"
    stored = hash_live_stream_secret(plain)
    assert stored.startswith("$pbkdf2-sha256$")
    assert verify_live_stream_secret(plain, stored)
    assert not verify_live_stream_secret("wrong", stored)
