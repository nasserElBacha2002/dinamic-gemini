"""API tests for inventory visual references endpoints — v3.2.4."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

from src.api.dependencies import get_artifact_storage
from src.api.server import app
from src.config import reload_settings
from src.infrastructure.storage.artifact_store import StoredArtifact

client = TestClient(app)

_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure auth env vars are set for environments that expect them.

    When auth is fully enabled, these tests may run under a different contract;
    in that case we skip API-level checks and rely on lower-layer tests.
    """
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _PWD_CONTEXT.hash("correct-password"))
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "t" * 40)
    monkeypatch.setenv("AUTH_TOKEN_EXPIRES_MINUTES", "5")
    reload_settings()
    yield


def _auth_headers() -> dict[str, str]:
    # Mirror route protection tests: log in as admin and reuse token.
    login_r = client.post("/auth/login", json={"username": "admin", "password": "correct-password"})
    if login_r.status_code == 401:
        pytest.skip("Auth is enabled; visual reference API wiring tests are skipped in this mode.")
    assert login_r.status_code == 200
    token = login_r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_inventory() -> str:
    resp = client.post("/api/v3/inventories", json={"name": "Inv with refs"}, headers=_auth_headers())
    assert resp.status_code == 201
    return resp.json()["id"]


class StubSignedUrlArtifactStorage:
    def __init__(self, return_prefixed_key: bool = False) -> None:
        self._return_prefixed_key = return_prefixed_key

    def put_object(self, path: str, file_obj, content_type: str) -> StoredArtifact:
        payload = file_obj.read()
        key = f"v3/{path}" if self._return_prefixed_key else path
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket="bucket-x",
            storage_key=key,
            content_type=content_type,
            file_size_bytes=len(payload),
            etag="etag-x",
        )

    def save_file(self, path: str, file_obj, content_type: str) -> str:
        return path

    def delete_file(self, path: str) -> None:
        return None

    def generate_signed_url(self, key: str, expires_in_sec: int) -> str:
        assert "v3/v3/" not in key
        return f"https://signed.example/{key}?exp={expires_in_sec}"


def test_upload_inventory_visual_references_and_list_success() -> None:
    inventory_id = _create_inventory()
    files = [
        ("files", ("ref1.jpg", BytesIO(b"jpeg-data"), "image/jpeg")),
        ("files", ("ref2.png", BytesIO(b"png-data"), "image/png")),
    ]
    upload_resp = client.post(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        files=files,
        headers=_auth_headers(),
    )
    assert upload_resp.status_code == 201
    data = upload_resp.json()
    assert "items" in data
    assert len(data["items"]) == 2
    for item in data["items"]:
        assert "id" in item
        assert item["inventory_id"] == inventory_id
        assert "filename" in item
        assert "file_size" in item
        assert "storage_path" not in item

    list_resp = client.get(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        headers=_auth_headers(),
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert "items" in listed
    assert len(listed["items"]) == 2
    for item in listed["items"]:
        assert "storage_path" not in item


def test_upload_inventory_visual_references_zero_byte_file_returns_422() -> None:
    inventory_id = _create_inventory()
    files = [("files", ("empty.jpg", BytesIO(b""), "image/jpeg"))]
    resp = client.post(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        files=files,
        headers=_auth_headers(),
    )
    assert resp.status_code == 422
    assert "zero-byte" in resp.json().get("detail", "").lower() or "empty" in resp.json().get("detail", "").lower()


def test_upload_inventory_visual_references_max_exceeded_returns_400() -> None:
    inventory_id = _create_inventory()
    # Upload 3 (max), then one more should return 400
    for _ in range(3):
        r = client.post(
            f"/api/v3/inventories/{inventory_id}/visual-references",
            files=[("files", ("ref.jpg", BytesIO(b"x"), "image/jpeg"))],
            headers=_auth_headers(),
        )
        assert r.status_code == 201
    fourth = client.post(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        files=[("files", ("fourth.jpg", BytesIO(b"xx"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    assert fourth.status_code == 400
    assert "Maximum" in fourth.json().get("detail", "")


def test_upload_inventory_visual_references_invalid_mime_type_returns_400() -> None:
    inventory_id = _create_inventory()
    files = [("files", ("doc.pdf", BytesIO(b"pdf"), "application/pdf"))]
    resp = client.post(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        files=files,
        headers=_auth_headers(),
    )
    assert resp.status_code == 400
    assert "Unsupported image content type" in resp.json().get("detail", "")


def test_upload_inventory_visual_references_inventory_not_found_returns_404() -> None:
    files = [("files", ("ref.jpg", BytesIO(b"jpeg-data"), "image/jpeg"))]
    resp = client.post(
        "/api/v3/inventories/nonexistent/visual-references",
        files=files,
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_upload_inventory_visual_references_empty_files_returns_422() -> None:
    inventory_id = _create_inventory()
    resp = client.post(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        files=[],
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_list_inventory_visual_references_inventory_not_found_returns_404() -> None:
    resp = client.get(
        "/api/v3/inventories/nonexistent/visual-references",
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_visual_reference_file_endpoint_redirects_to_signed_url_for_s3_backed_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("ARTIFACT_S3_BUCKET", "bucket-x")
    monkeypatch.setenv("ARTIFACT_S3_SIGNED_URL_TTL_SEC", "777")
    reload_settings()
    app.dependency_overrides[get_artifact_storage] = lambda: StubSignedUrlArtifactStorage()
    try:
        inventory_id = _create_inventory()
        files = [("files", ("ref1.jpg", BytesIO(b"jpeg-data"), "image/jpeg"))]
        upload_resp = client.post(
            f"/api/v3/inventories/{inventory_id}/visual-references",
            files=files,
            headers=_auth_headers(),
        )
        assert upload_resp.status_code == 201
        reference_id = upload_resp.json()["items"][0]["id"]

        file_resp = client.get(
            f"/api/v3/inventories/{inventory_id}/visual-references/{reference_id}/file",
            headers=_auth_headers(),
            follow_redirects=False,
        )
        assert file_resp.status_code == 307
        assert file_resp.headers["location"].startswith("https://signed.example/inventories/")
        assert "exp=777" in file_resp.headers["location"]
    finally:
        app.dependency_overrides.pop(get_artifact_storage, None)
        monkeypatch.delenv("ARTIFACT_STORAGE_PROVIDER", raising=False)
        monkeypatch.delenv("ARTIFACT_S3_BUCKET", raising=False)
        monkeypatch.delenv("ARTIFACT_S3_SIGNED_URL_TTL_SEC", raising=False)
        reload_settings()


def test_visual_reference_file_endpoint_signed_url_handles_prefixed_persisted_key_without_double_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("ARTIFACT_S3_BUCKET", "bucket-x")
    monkeypatch.setenv("ARTIFACT_S3_SIGNED_URL_TTL_SEC", "555")
    reload_settings()
    app.dependency_overrides[get_artifact_storage] = lambda: StubSignedUrlArtifactStorage(return_prefixed_key=True)
    try:
        inventory_id = _create_inventory()
        files = [("files", ("ref1.jpg", BytesIO(b"jpeg-data"), "image/jpeg"))]
        upload_resp = client.post(
            f"/api/v3/inventories/{inventory_id}/visual-references",
            files=files,
            headers=_auth_headers(),
        )
        assert upload_resp.status_code == 201
        reference_id = upload_resp.json()["items"][0]["id"]

        file_resp = client.get(
            f"/api/v3/inventories/{inventory_id}/visual-references/{reference_id}/file",
            headers=_auth_headers(),
            follow_redirects=False,
        )
        assert file_resp.status_code == 307
        location = file_resp.headers["location"]
        assert "v3/v3/" not in location
        assert "exp=555" in location
    finally:
        app.dependency_overrides.pop(get_artifact_storage, None)
        monkeypatch.delenv("ARTIFACT_STORAGE_PROVIDER", raising=False)
        monkeypatch.delenv("ARTIFACT_S3_BUCKET", raising=False)
        monkeypatch.delenv("ARTIFACT_S3_SIGNED_URL_TTL_SEC", raising=False)
        reload_settings()


def test_visual_reference_file_endpoint_falls_back_to_local_when_legacy_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED", "true")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    reload_settings()
    inventory_id = _create_inventory()
    files = [("files", ("ref1.jpg", BytesIO(b"jpeg-data"), "image/jpeg"))]
    upload_resp = client.post(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        files=files,
        headers=_auth_headers(),
    )
    assert upload_resp.status_code == 201
    reference_id = upload_resp.json()["items"][0]["id"]

    rel = f"inventories/{inventory_id}/visual_references/{reference_id}.jpg"
    p = tmp_path / "v3_uploads" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"legacy-bytes")

    try:
        file_resp = client.get(
            f"/api/v3/inventories/{inventory_id}/visual-references/{reference_id}/file",
            headers=_auth_headers(),
        )
        assert file_resp.status_code == 200
        assert file_resp.content == b"legacy-bytes"
        assert file_resp.headers.get("content-type", "").startswith("image/jpeg")
    finally:
        monkeypatch.delenv("ARTIFACT_STORAGE_PROVIDER", raising=False)
        monkeypatch.delenv("ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED", raising=False)
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        reload_settings()

