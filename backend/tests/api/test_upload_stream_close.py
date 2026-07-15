"""Uploaded file streams must always be closed after the request, on success and on failure."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_artifact_storage,
    get_upload_aisle_assets_use_case,
    get_upload_capture_session_staging_items_use_case,
)
from src.api.routes.v3 import assets as assets_route
from src.api.routes.v3 import capture_sessions as capture_sessions_route
from src.api.server import app
from src.api.services import multipart_aisle_uploads as multipart_aisle_uploads_mod
from src.application.services import upload_stream_io as upload_stream_io_mod
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from tests.support.api_v3_test_helpers import create_test_inventory, create_test_supplier


@pytest.fixture
def client_v3(tmp_path: Path) -> TestClient:
    def _fake_admin() -> AuthUser:
        return AuthUser(id="admin", username="admin", role="administrator")

    store = V3ArtifactStorageAdapter(tmp_path / "artifacts")
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_artifact_storage] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class _BoomUseCase:
    """Stand-in use case whose execute() always raises, to exercise the finally-block close."""

    def execute(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated use case failure")


def _create_inventory_and_aisle(client_v3: TestClient, code: str) -> tuple[str, str]:
    create = create_test_inventory(client_v3, name=f"Close Stream {code}")
    assert create.status_code == 201, create.text
    inv_id = create.json()["id"]
    inv = client_v3.get(f"/api/v3/inventories/{inv_id}").json()
    sid = create_test_supplier(client_v3, inv["client_id"])
    aisle_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": code, "client_supplier_id": sid},
    )
    assert aisle_resp.status_code == 201, aisle_resp.text
    return inv_id, aisle_resp.json()["id"]


def test_upload_aisle_assets_closes_file_streams_on_success(
    monkeypatch: pytest.MonkeyPatch, client_v3: TestClient
) -> None:
    closed: list[bool] = []
    original = assets_route.close_uploaded_files

    def spy(files: object) -> None:
        original(files)
        closed.append(all(uf.file_obj.closed for uf in files))

    monkeypatch.setattr(assets_route, "close_uploaded_files", spy)
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CLOSE-OK")

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[("files", ("a.jpg", b"fake_jpeg", "image/jpeg"))],
    )

    assert resp.status_code == 201, resp.text
    assert closed == [True]


def test_upload_aisle_assets_closes_file_streams_on_use_case_failure(
    monkeypatch: pytest.MonkeyPatch, client_v3: TestClient
) -> None:
    closed: list[bool] = []
    original = assets_route.close_uploaded_files

    def spy(files: object) -> None:
        original(files)
        closed.append(all(uf.file_obj.closed for uf in files))

    monkeypatch.setattr(assets_route, "close_uploaded_files", spy)
    app.dependency_overrides[get_upload_aisle_assets_use_case] = lambda: _BoomUseCase()
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CLOSE-FAIL")

    # Starlette's ServerErrorMiddleware always re-raises after invoking the registered
    # Exception handler (so test clients can assert on it); the route's own ``finally`` block
    # still runs first, which is what this test cares about.
    with pytest.raises(RuntimeError, match="simulated use case failure"):
        client_v3.post(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
            files=[("files", ("a.jpg", b"fake_jpeg", "image/jpeg"))],
        )

    assert closed == [True]


def test_capture_session_staging_upload_closes_file_streams_on_success(
    monkeypatch: pytest.MonkeyPatch, client_v3: TestClient
) -> None:
    closed: list[bool] = []
    original = capture_sessions_route.close_uploaded_files

    def spy(files: object) -> None:
        original(files)
        closed.append(all(uf.file_obj.closed for uf in files))

    monkeypatch.setattr(capture_sessions_route, "close_uploaded_files", spy)
    create = create_test_inventory(client_v3, name="Close Stream Staging OK")
    assert create.status_code == 201, create.text
    inv_id = create.json()["id"]
    session_resp = client_v3.post(f"/api/v3/inventories/{inv_id}/capture-sessions")
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["id"]

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/capture-sessions/{session_id}/items",
        files=[("files", ("a.jpg", b"fake_jpeg", "image/jpeg"))],
    )

    assert resp.status_code == 201, resp.text
    assert closed == [True]


def test_capture_session_staging_upload_closes_file_streams_on_use_case_failure(
    monkeypatch: pytest.MonkeyPatch, client_v3: TestClient
) -> None:
    closed: list[bool] = []
    original = capture_sessions_route.close_uploaded_files

    def spy(files: object) -> None:
        original(files)
        closed.append(all(uf.file_obj.closed for uf in files))

    monkeypatch.setattr(capture_sessions_route, "close_uploaded_files", spy)
    app.dependency_overrides[get_upload_capture_session_staging_items_use_case] = (
        lambda: _BoomUseCase()
    )
    create = create_test_inventory(client_v3, name="Close Stream Staging Fail")
    assert create.status_code == 201, create.text
    inv_id = create.json()["id"]
    session_resp = client_v3.post(f"/api/v3/inventories/{inv_id}/capture-sessions")
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["id"]

    with pytest.raises(RuntimeError, match="simulated use case failure"):
        client_v3.post(
            f"/api/v3/inventories/{inv_id}/capture-sessions/{session_id}/items",
            files=[("files", ("a.jpg", b"fake_jpeg", "image/jpeg"))],
        )

    assert closed == [True]


def test_aisle_scoped_capture_session_staging_upload_closes_file_streams_on_success(
    monkeypatch: pytest.MonkeyPatch, client_v3: TestClient
) -> None:
    """Third endpoint: POST .../aisles/{aisle_id}/capture-sessions/{session_id}/items."""
    closed: list[bool] = []
    original = capture_sessions_route.close_uploaded_files

    def spy(files: object) -> None:
        original(files)
        closed.append(all(uf.file_obj.closed for uf in files))

    monkeypatch.setattr(capture_sessions_route, "close_uploaded_files", spy)
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CLOSE-AISLE-CAP")
    session_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions"
    )
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["id"]

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items",
        files=[("files", ("a.jpg", b"fake_jpeg", "image/jpeg"))],
    )

    assert resp.status_code == 201, resp.text
    assert closed == [True]


def _track_all_spooled_tempfiles(monkeypatch: pytest.MonkeyPatch) -> list:
    """Wrap ``tempfile.SpooledTemporaryFile`` so every instance created during the request
    (successful or abandoned mid-spool) is recorded, regardless of which code path closes it."""
    created: list = []
    original_cls = tempfile.SpooledTemporaryFile

    class _TrackingSpooled(original_cls):  # type: ignore[misc]
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(upload_stream_io_mod.tempfile, "SpooledTemporaryFile", _TrackingSpooled)
    return created


def _tiny_limits_settings() -> SimpleNamespace:
    return SimpleNamespace(
        max_files_per_upload_request=10,
        max_upload_file_size_mb=1,
        max_upload_request_size_mb=10,
    )


def test_aisle_assets_upload_closes_all_spooled_files_when_a_later_file_exceeds_size_limit(
    monkeypatch: pytest.MonkeyPatch, client_v3: TestClient
) -> None:
    """Regression: if the Nth file in a multi-file request exceeds the per-file size cap, every
    ``SpooledTemporaryFile`` created for the request so far (including the failing one) must be
    closed — no leaked temp files/handles on partial failure."""
    created = _track_all_spooled_tempfiles(monkeypatch)
    monkeypatch.setattr(multipart_aisle_uploads_mod, "load_settings", _tiny_limits_settings)
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CLOSE-2ND-FAIL")

    oversized = b"x" * (2 * 1024 * 1024)  # 2MB > the 1MB cap patched above
    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[
            ("files", ("a.jpg", b"fake_jpeg_ok", "image/jpeg")),
            ("files", ("b.jpg", oversized, "image/jpeg")),
        ],
    )

    assert resp.status_code == 422, resp.text
    assert len(created) == 2
    assert all(f.closed for f in created)


def test_capture_session_staging_upload_closes_all_spooled_files_when_a_later_file_exceeds_size_limit(
    monkeypatch: pytest.MonkeyPatch, client_v3: TestClient
) -> None:
    """Same regression as above, for the capture-session staging upload endpoint."""
    created = _track_all_spooled_tempfiles(monkeypatch)
    monkeypatch.setattr(multipart_aisle_uploads_mod, "load_settings", _tiny_limits_settings)
    create = create_test_inventory(client_v3, name="Close Stream Staging Partial")
    assert create.status_code == 201, create.text
    inv_id = create.json()["id"]
    session_resp = client_v3.post(f"/api/v3/inventories/{inv_id}/capture-sessions")
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["id"]

    oversized = b"x" * (2 * 1024 * 1024)
    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/capture-sessions/{session_id}/items",
        files=[
            ("files", ("a.jpg", b"fake_jpeg_ok", "image/jpeg")),
            ("files", ("b.jpg", oversized, "image/jpeg")),
        ],
    )

    assert resp.status_code == 422, resp.text
    assert len(created) == 2
    assert all(f.closed for f in created)
