"""POST /api/v3/admin/storage/cleanup — primary admin gate + dry-run/delete guards."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.api.dependencies import get_artifact_storage
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser


def _restore_overrides() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    app.dependency_overrides[get_artifact_storage] = lambda: MagicMock()


def test_storage_cleanup_dry_run_200_for_primary_admin(monkeypatch) -> None:
    from src.application.use_cases import admin_storage_cleanup as mod
    from src.infrastructure.storage.artifact_storage_maintenance import (
        LocalCleanupSection,
        RemoteCleanupSection,
        StorageCleanupResult,
    )

    mock_result = StorageCleanupResult(
        ok=True,
        mode="dry_run",
        target="both",
        remote=RemoteCleanupSection(provider="gcs", bucket="b", prefix="v3", objects_found=2),
        local=LocalCleanupSection(
            output_dir="output", safe_roots=["output/v3_uploads"], files_found=1
        ),
    )
    monkeypatch.setattr(
        mod.AdminStorageCleanupUseCase,
        "execute",
        lambda self, **kwargs: mock_result,
    )
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v3/admin/storage/cleanup",
            json={"target": "both", "mode": "dry_run"},
        )
    finally:
        _restore_overrides()

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "dry_run"
    assert body["remote"]["objects_found"] == 2
    assert body["local"]["files_found"] == 1


def test_storage_cleanup_401_without_auth() -> None:
    app.dependency_overrides.pop(get_current_admin, None)
    try:
        client = TestClient(app)
        r = client.post("/api/v3/admin/storage/cleanup", json={"mode": "dry_run"})
        assert r.status_code == 401
    finally:
        _restore_overrides()


def test_storage_cleanup_403_for_jairo() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="jairo", username="Jairo", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.post("/api/v3/admin/storage/cleanup", json={"mode": "dry_run"})
        assert r.status_code == 403
    finally:
        _restore_overrides()


def test_storage_cleanup_delete_requires_confirm() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v3/admin/storage/cleanup",
            json={"mode": "delete", "confirm": "WRONG"},
        )
        assert r.status_code == 400
    finally:
        _restore_overrides()
