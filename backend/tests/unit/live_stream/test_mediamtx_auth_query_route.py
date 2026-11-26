"""AuthHTTP accepts credentials embedded in the path query string (DJI single-field URL)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps.live_stream import get_mediamtx_auth_service
from src.api.routes.internal_mediamtx_auth import router
from src.application.services.live_stream_credential_crypto import hash_live_stream_secret
from src.application.services.mediamtx_auth_service import MediaMtxAuthService
from src.domain.live_stream.entities import LiveChannelCredentials
from src.infrastructure.repositories.memory_live_stream_repository import MemoryLiveStreamRepository

SECRET = "test-mtx-callback-secret"
PATH = "live/prueba-26-11/01"


@pytest.fixture
def mtx_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MEDIAMTX_HTTP_AUTH_SECRET", SECRET)
    monkeypatch.setenv("LIVE_STREAM_ENABLED", "true")
    monkeypatch.setenv("LIVE_STREAM_FIXED_PUBLISH_USERNAME", "nasser")
    monkeypatch.setenv("LIVE_STREAM_FIXED_PUBLISH_PASSWORD", "Libano02")
    from datetime import datetime, timezone
    from uuid import uuid4

    from src.config import reload_settings

    reload_settings()

    repo = MemoryLiveStreamRepository()
    now = datetime.now(timezone.utc)
    repo.upsert_channel_credentials(
        LiveChannelCredentials(
            id=str(uuid4()),
            inventory_id="inv",
            canonical_aisle_code="01",
            channel_slug="01",
            mediamtx_path=PATH,
            publish_username="nasser",
            publish_password_hash=hash_live_stream_secret("Libano02"),
            read_username="nasser",
            read_password_hash=hash_live_stream_secret("Libano02"),
            created_by_principal_id="admin",
            created_at=now,
            updated_at=now,
        )
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mediamtx_auth_service] = lambda: MediaMtxAuthService(
        repo=repo,
        server_secret="unit-secret",
        enabled=True,
        fixed_publish_username="nasser",
        fixed_publish_password="Libano02",
    )
    return TestClient(app)


def test_auth_accepts_path_query_only(mtx_client: TestClient) -> None:
    resp = mtx_client.post(
        f"/api/internal/mediamtx/auth?mtx_key={SECRET}",
        json={
            "user": "",
            "password": "",
            "path": f"{PATH}?user=nasser&pass=Libano02",
            "action": "publish",
            "protocol": "rtmp",
        },
    )
    assert resp.status_code == 200
