"""GET /api/v3/config/upload-limits — client-facing upload sizing/concurrency hints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.config import load_settings


@pytest.fixture
def client_v3() -> TestClient:
    def _fake_admin() -> AuthUser:
        return AuthUser(id="admin", username="admin", role="administrator")

    app.dependency_overrides[get_current_admin] = _fake_admin
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_upload_limits_returns_settings_derived_values(client_v3: TestClient) -> None:
    settings = load_settings()

    resp = client_v3.get("/api/v3/config/upload-limits")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["max_files_per_request"] == settings.max_files_per_upload_request
    assert body["max_file_size_bytes"] == settings.max_upload_file_size_mb * 1024 * 1024
    assert body["max_request_size_bytes"] == settings.max_upload_request_size_mb * 1024 * 1024
    assert body["upload_batch_concurrency"] == settings.upload_batch_concurrency
    assert body["retry_attempts"] == settings.upload_retry_attempts
    assert body["retry_base_delay_ms"] == settings.upload_retry_base_delay_ms
