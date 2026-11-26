"""MediaMTX auth service tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.application.services.live_stream_credential_crypto import (
    derive_channel_password,
    derive_public_grant_password,
    hash_public_token,
    mint_stream_username,
)
from src.application.services.mediamtx_auth_service import MediaMtxAuthService
from src.domain.live_stream.entities import LiveChannelCredentials, LiveViewGrant
from src.infrastructure.repositories.memory_live_stream_repository import MemoryLiveStreamRepository

SECRET = "unit-test-secret"
PATH = "live/550e8400-e29b-41d4-a716-446655440001/abc123"


def _seed_channel(repo: MemoryLiveStreamRepository) -> LiveChannelCredentials:
    now = datetime.now(timezone.utc)
    pub_user = mint_stream_username("pub", "abc123")
    read_user = mint_stream_username("view", "abc123")
    record = LiveChannelCredentials(
        id=str(uuid4()),
        inventory_id="550e8400-e29b-41d4-a716-446655440001",
        canonical_aisle_code="A01",
        channel_slug="abc123",
        mediamtx_path=PATH,
        publish_username=pub_user,
        publish_password_hash="",
        read_username=read_user,
        read_password_hash="",
        created_by_principal_id="admin",
        created_at=now,
        updated_at=now,
    )
    repo.upsert_channel_credentials(record)
    return record


def test_publish_and_read_separated() -> None:
    repo = MemoryLiveStreamRepository()
    record = _seed_channel(repo)
    svc = MediaMtxAuthService(repo=repo, server_secret=SECRET, enabled=True)
    pub_pass = derive_channel_password(server_secret=SECRET, mediamtx_path=PATH, purpose="publish")
    read_pass = derive_channel_password(server_secret=SECRET, mediamtx_path=PATH, purpose="read")
    assert svc.authorize(
        username=record.publish_username,
        password=pub_pass,
        path=PATH,
        action="publish",
    ).allowed
    assert not svc.authorize(
        username=record.publish_username,
        password=read_pass,
        path=PATH,
        action="publish",
    ).allowed
    assert svc.authorize(
        username=record.read_username,
        password=read_pass,
        path=PATH,
        action="read",
    ).allowed
    assert not svc.authorize(
        username=record.read_username,
        password=pub_pass,
        path=PATH,
        action="publish",
    ).allowed


def test_same_username_publish_and_read_for_fixed_credentials() -> None:
    repo = MemoryLiveStreamRepository()
    now = datetime.now(timezone.utc)
    fixed_user = "nasser"
    record = LiveChannelCredentials(
        id=str(uuid4()),
        inventory_id="550e8400-e29b-41d4-a716-446655440001",
        canonical_aisle_code="P1",
        channel_slug="abc123",
        mediamtx_path="live/Prueba18-09/P1",
        publish_username=fixed_user,
        publish_password_hash="",
        read_username=fixed_user,
        read_password_hash="",
        created_by_principal_id="admin",
        created_at=now,
        updated_at=now,
    )
    repo.upsert_channel_credentials(record)
    svc = MediaMtxAuthService(repo=repo, server_secret=SECRET, enabled=True)
    read_pass = derive_channel_password(
        server_secret=SECRET,
        mediamtx_path=record.mediamtx_path,
        purpose="read",
    )
    pub_pass = derive_channel_password(
        server_secret=SECRET,
        mediamtx_path=record.mediamtx_path,
        purpose="publish",
    )
    assert svc.authorize(
        username=fixed_user,
        password=pub_pass,
        path=record.mediamtx_path,
        action="publish",
    ).allowed
    assert svc.authorize(
        username=fixed_user,
        password=read_pass,
        path=record.mediamtx_path,
        action="read",
    ).allowed
    assert svc.authorize(
        username=fixed_user,
        password=pub_pass,
        path=record.mediamtx_path,
        action="read",
    ).allowed is False


def test_publish_allows_empty_path_for_known_publisher() -> None:
    repo = MemoryLiveStreamRepository()
    record = _seed_channel(repo)
    svc = MediaMtxAuthService(repo=repo, server_secret=SECRET, enabled=True)
    pub_pass = derive_channel_password(server_secret=SECRET, mediamtx_path=PATH, purpose="publish")
    assert svc.authorize(
        username=record.publish_username,
        password=pub_pass,
        path="",
        action="publish",
    ).allowed


def test_publish_by_path_with_fixed_env_password() -> None:
    repo = MemoryLiveStreamRepository()
    now = datetime.now(timezone.utc)
    mediamtx_path = "live/prueba-26-11/01"
    record = LiveChannelCredentials(
        id=str(uuid4()),
        inventory_id="inv-1",
        canonical_aisle_code="01",
        channel_slug="01",
        mediamtx_path=mediamtx_path,
        publish_username="nasser",
        publish_password_hash="",
        read_username="nasser",
        read_password_hash="",
        created_by_principal_id="admin",
        created_at=now,
        updated_at=now,
    )
    repo.upsert_channel_credentials(record)
    svc = MediaMtxAuthService(
        repo=repo,
        server_secret=SECRET,
        enabled=True,
        fixed_publish_username="nasser",
        fixed_publish_password="Libano02",
    )
    assert svc.authorize(
        username="nasser",
        password="Libano02",
        path=mediamtx_path,
        action="publish",
    ).allowed


def test_publish_by_path_requires_publish_password_not_read() -> None:
    repo = MemoryLiveStreamRepository()
    _seed_channel(repo)
    svc = MediaMtxAuthService(repo=repo, server_secret=SECRET, enabled=True)
    read_pass = derive_channel_password(server_secret=SECRET, mediamtx_path=PATH, purpose="read")
    assert not svc.authorize(
        username="",
        password=read_pass,
        path=PATH,
        action="publish",
    ).allowed


def test_publish_allows_stream_key_suffix() -> None:
    repo = MemoryLiveStreamRepository()
    record = _seed_channel(repo)
    svc = MediaMtxAuthService(repo=repo, server_secret=SECRET, enabled=True)
    pub_pass = derive_channel_password(server_secret=SECRET, mediamtx_path=PATH, purpose="publish")
    assert svc.authorize(
        username=record.publish_username,
        password=pub_pass,
        path="abc123",
        action="publish",
    ).allowed


def test_cross_path_denied() -> None:
    repo = MemoryLiveStreamRepository()
    record = _seed_channel(repo)
    svc = MediaMtxAuthService(repo=repo, server_secret=SECRET, enabled=True)
    pub_pass = derive_channel_password(server_secret=SECRET, mediamtx_path=PATH, purpose="publish")
    other = PATH + "-other"
    assert not svc.authorize(
        username=record.publish_username,
        password=pub_pass,
        path=other,
        action="publish",
    ).allowed


def test_public_grant_expired() -> None:
    repo = MemoryLiveStreamRepository()
    now = datetime.now(timezone.utc)
    grant_id = str(uuid4())
    view_user = mint_stream_username("pubview", "abc123")
    grant = LiveViewGrant(
        id=grant_id,
        inventory_id="550e8400-e29b-41d4-a716-446655440001",
        channel_slug="abc123",
        mediamtx_path=PATH,
        token_hash=hash_public_token("token"),
        view_username=view_user,
        view_password_hash="",
        created_by_principal_id="admin",
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=1),
        revoked_at=None,
    )
    repo.save_view_grant(grant)
    svc = MediaMtxAuthService(repo=repo, server_secret=SECRET, enabled=True)
    view_pass = derive_public_grant_password(server_secret=SECRET, grant_id=grant_id)
    assert not svc.authorize(
        username=view_user,
        password=view_pass,
        path=PATH,
        action="read",
        now=now,
    ).allowed
