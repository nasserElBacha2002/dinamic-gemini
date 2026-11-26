"""Revoke public grant scoped by inventory_id."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.application.services.live_stream_credential_crypto import hash_public_token, mint_stream_username
from src.domain.live_stream.entities import LiveViewGrant
from src.infrastructure.repositories.memory_live_stream_repository import MemoryLiveStreamRepository

INV_A = "550e8400-e29b-41d4-a716-446655440001"
INV_B = "550e8400-e29b-41d4-a716-446655440002"
PATH = "live/x/abc"


def _grant(*, inv: str, grant_id: str) -> LiveViewGrant:
    now = datetime.now(timezone.utc)
    return LiveViewGrant(
        id=grant_id,
        inventory_id=inv,
        channel_slug="abc",
        mediamtx_path=PATH,
        token_hash=hash_public_token(grant_id),
        view_username=mint_stream_username("pubview", "abc"),
        view_password_hash="hash",
        created_by_principal_id="admin",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        revoked_at=None,
    )


def test_cannot_revoke_grant_from_other_inventory() -> None:
    repo = MemoryLiveStreamRepository()
    grant_id = str(uuid4())
    repo.save_view_grant(_grant(inv=INV_A, grant_id=grant_id))
    now = datetime.now(timezone.utc)
    assert not repo.revoke_view_grant(grant_id, inventory_id=INV_B, revoked_at=now)
    kept = repo.get_view_grant_by_token_hash(hash_public_token(grant_id))
    assert kept is not None
    assert kept.revoked_at is None


def test_revoke_success_same_inventory() -> None:
    repo = MemoryLiveStreamRepository()
    grant_id = str(uuid4())
    repo.save_view_grant(_grant(inv=INV_A, grant_id=grant_id))
    now = datetime.now(timezone.utc)
    assert repo.revoke_view_grant(grant_id, inventory_id=INV_A, revoked_at=now)
    kept = repo.get_view_grant_by_token_hash(hash_public_token(grant_id))
    assert kept is not None
    assert kept.revoked_at == now