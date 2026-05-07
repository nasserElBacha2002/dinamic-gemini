"""API tests for inventory visual references endpoints — v3.2.4 + Phase C8 (writes disabled via HTTP)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

import src.config as config_module
from src.api.constants.error_wire import HTTP_DETAIL_LEGACY_INVENTORY_VISUAL_REFERENCES_DISABLED
from src.api.dependencies import get_artifact_storage
from src.api.errors.structured_api_http import LEGACY_INVENTORY_VISUAL_REFERENCES_DISABLED
from src.api.server import app
from src.application.use_cases.upload_inventory_visual_references import (
    UploadedVisualReferenceFile,
    UploadInventoryVisualReferencesUseCase,
)
from src.config import AppSettings, reload_settings
from src.infrastructure.storage.artifact_store import StoredArtifact
from src.runtime.app_container import get_app_container, reset_app_container_for_tests

client = TestClient(app)

_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _PWD_CONTEXT.hash("correct-password"))
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "t" * 40)
    monkeypatch.setenv("AUTH_TOKEN_EXPIRES_MINUTES", "5")
    reload_settings()
    yield


def _auth_headers() -> dict[str, str]:
    login_r = client.post("/auth/login", json={"username": "admin", "password": "correct-password"})
    if login_r.status_code == 401:
        pytest.skip("Auth is enabled; visual reference API wiring tests are skipped in this mode.")
    assert login_r.status_code == 200
    token = login_r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_inventory() -> str:
    resp = client.post(
        "/api/v3/inventories", json={"name": "Inv with refs"}, headers=_auth_headers()
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _assert_legacy_writes_disabled(resp) -> None:
    assert resp.status_code == 410
    body = resp.json()
    assert body["code"] == LEGACY_INVENTORY_VISUAL_REFERENCES_DISABLED
    assert body["detail"] == HTTP_DETAIL_LEGACY_INVENTORY_VISUAL_REFERENCES_DISABLED


def _seed_visual_reference(inventory_id: str, *, artifact_storage=None) -> str:
    """Insert a visual reference row + artifact without using the disabled POST endpoint."""
    c = get_app_container()
    storage = artifact_storage if artifact_storage is not None else c.get_artifact_storage()
    uc = UploadInventoryVisualReferencesUseCase(
        inventory_repo=c.get_inventory_repo(),
        reference_repo=c.get_inventory_visual_reference_repo(),
        artifact_storage=storage,
        clock=c.get_clock(),
    )
    refs = uc.execute(
        inventory_id,
        [
            UploadedVisualReferenceFile(
                original_filename="ref1.jpg",
                file_obj=BytesIO(b"jpeg-data"),
                content_type="image/jpeg",
                size=len(b"jpeg-data"),
            )
        ],
    )
    return refs[0].id


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


def test_post_inventory_visual_references_returns_410_structured_error() -> None:
    inventory_id = _create_inventory()
    files = [
        ("files", ("ref1.jpg", BytesIO(b"jpeg-data"), "image/jpeg")),
    ]
    resp = client.post(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        files=files,
        headers=_auth_headers(),
    )
    _assert_legacy_writes_disabled(resp)

    list_resp = client.get(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        headers=_auth_headers(),
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["items"] == []


def test_put_inventory_visual_reference_returns_410_structured_error() -> None:
    inventory_id = _create_inventory()
    reference_id = _seed_visual_reference(inventory_id)
    resp = client.put(
        f"/api/v3/inventories/{inventory_id}/visual-references/{reference_id}",
        files={"file": ("replacement.png", BytesIO(b"png-data"), "image/png")},
        headers=_auth_headers(),
    )
    _assert_legacy_writes_disabled(resp)


def test_delete_inventory_visual_reference_returns_410_structured_error() -> None:
    inventory_id = _create_inventory()
    reference_id = _seed_visual_reference(inventory_id)
    resp = client.delete(
        f"/api/v3/inventories/{inventory_id}/visual-references/{reference_id}",
        headers=_auth_headers(),
    )
    _assert_legacy_writes_disabled(resp)

    list_resp = client.get(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        headers=_auth_headers(),
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) == 1


def test_post_inventory_visual_references_unknown_inventory_still_returns_410() -> None:
    files = [("files", ("ref.jpg", BytesIO(b"jpeg-data"), "image/jpeg"))]
    resp = client.post(
        "/api/v3/inventories/nonexistent/visual-references",
        files=files,
        headers=_auth_headers(),
    )
    _assert_legacy_writes_disabled(resp)


def test_list_inventory_visual_references_inventory_not_found_returns_404() -> None:
    resp = client.get(
        "/api/v3/inventories/nonexistent/visual-references",
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_list_inventory_visual_references_returns_seeded_rows() -> None:
    inventory_id = _create_inventory()
    reference_id = _seed_visual_reference(inventory_id)
    list_resp = client.get(
        f"/api/v3/inventories/{inventory_id}/visual-references",
        headers=_auth_headers(),
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == reference_id
    assert items[0]["inventory_id"] == inventory_id
    assert "storage_path" not in items[0]


def test_visual_reference_file_endpoint_redirects_to_signed_url_for_s3_backed_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("ARTIFACT_S3_BUCKET", "bucket-x")
    monkeypatch.setenv("ARTIFACT_S3_SIGNED_URL_TTL_SEC", "777")
    reload_settings()
    reset_app_container_for_tests()
    stub = StubSignedUrlArtifactStorage()
    app.dependency_overrides[get_artifact_storage] = lambda: stub
    try:
        inventory_id = _create_inventory()
        reference_id = _seed_visual_reference(inventory_id, artifact_storage=stub)

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
        reset_app_container_for_tests()


def test_visual_reference_file_endpoint_signed_url_handles_prefixed_persisted_key_without_double_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("ARTIFACT_S3_BUCKET", "bucket-x")
    monkeypatch.setenv("ARTIFACT_S3_SIGNED_URL_TTL_SEC", "555")
    reload_settings()
    reset_app_container_for_tests()
    stub = StubSignedUrlArtifactStorage(return_prefixed_key=True)
    app.dependency_overrides[get_artifact_storage] = lambda: stub
    try:
        inventory_id = _create_inventory()
        reference_id = _seed_visual_reference(inventory_id, artifact_storage=stub)

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
        reset_app_container_for_tests()


def test_visual_reference_file_endpoint_falls_back_to_local_when_legacy_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED", "true")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    config_module._settings = AppSettings()
    reset_app_container_for_tests()
    inventory_id = _create_inventory()
    reference_id = _seed_visual_reference(inventory_id)

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
        reset_app_container_for_tests()
