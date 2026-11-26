"""MediaMTX authHTTP route — mtx_key query (MediaMTX 1.11 compat)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps.live_stream import get_mediamtx_auth_service
from src.api.routes.internal_mediamtx_auth import router
from src.application.services.mediamtx_auth_service import MediaMtxAuthDecision, MediaMtxAuthService

SECRET = "test-mtx-callback-secret"


@pytest.fixture
def mtx_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MEDIAMTX_HTTP_AUTH_SECRET", SECRET)
    monkeypatch.setenv("LIVE_STREAM_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()

    app = FastAPI()
    app.include_router(router)

    class _AllowAuth(MediaMtxAuthService):
        def authorize(self, **kwargs):  # type: ignore[override]
            return MediaMtxAuthDecision(allowed=True)

    app.dependency_overrides[get_mediamtx_auth_service] = lambda: _AllowAuth(
        repo=__import__(
            "src.infrastructure.repositories.memory_live_stream_repository",
            fromlist=["MemoryLiveStreamRepository"],
        ).MemoryLiveStreamRepository(),
        server_secret="s",
        enabled=True,
    )
    return TestClient(app)


def test_auth_rejects_missing_mtx_key(mtx_client: TestClient) -> None:
    resp = mtx_client.post(
        "/api/internal/mediamtx/auth",
        json={"user": "u", "password": "p", "path": "live/x/y", "action": "read"},
    )
    assert resp.status_code == 401


def test_auth_accepts_mtx_key_query(mtx_client: TestClient) -> None:
    resp = mtx_client.post(
        f"/api/internal/mediamtx/auth?mtx_key={SECRET}",
        json={"user": "u", "password": "p", "path": "live/x/y", "action": "read"},
    )
    assert resp.status_code == 200
