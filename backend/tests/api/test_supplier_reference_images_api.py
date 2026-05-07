"""API tests for supplier reference images — Phase C2."""

from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

import src.config as config_module
from src.api.dependencies import get_artifact_storage
from src.api.errors.structured_api_http import (
    CLIENT_NOT_FOUND,
    CLIENT_SUPPLIER_CLIENT_MISMATCH,
    CLIENT_SUPPLIER_NOT_FOUND,
    SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
    UNSUPPORTED_ASSET_TYPE,
)
from src.api.server import app
from src.application.utils.supplier_reference_image_paths import (
    supplier_reference_image_storage_path,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.config import AppSettings, reload_settings
from src.infrastructure.storage.artifact_store import StoredArtifact
from src.runtime.app_container import reset_app_container_for_tests

client = TestClient(app)


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


@pytest.fixture(autouse=True)
def _admin_dependency_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Bypass Bearer login (parallel to aisle wiring tests); routes still require admin dependency."""
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "t" * 40)
    monkeypatch.setenv("AUTH_TOKEN_EXPIRES_MINUTES", "5")
    reload_settings()
    app.dependency_overrides[get_current_admin] = _fake_admin
    yield
    app.dependency_overrides.pop(get_current_admin, None)


def _auth_headers() -> dict[str, str]:
    return {}


def _create_client(name: str = "Cliente refs") -> str:
    resp = client.post(
        "/api/v3/clients",
        json={"name": name, "status": "active"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 201
    return cast(str, resp.json()["id"])


def _create_supplier(client_id: str, name: str = "Proveedor refs") -> str:
    resp = client.post(
        f"/api/v3/clients/{client_id}/suppliers",
        json={"name": name, "status": "active"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 201
    return cast(str, resp.json()["id"])


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


def test_list_supplier_reference_images_empty() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    r = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_list_supplier_reference_images_returns_created_images() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    up = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
        files=[("files", ("a.jpg", BytesIO(b"jpeg-bytes"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    assert up.status_code == 201
    r = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["client_supplier_id"] == sid
    assert items[0]["filename"] == "a.jpg"
    for forbidden in ("storage_path", "storage_key", "storage_bucket", "etag"):
        assert forbidden not in items[0]


def test_list_supplier_reference_images_missing_client() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    r = client.get(
        f"/api/v3/clients/nonexistent-client/suppliers/{sid}/reference-images",
        headers=_auth_headers(),
    )
    assert r.status_code == 404
    body = r.json()
    assert body.get("code") == CLIENT_NOT_FOUND


def test_list_supplier_reference_images_missing_supplier() -> None:
    cid = _create_client()
    r = client.get(
        f"/api/v3/clients/{cid}/suppliers/no-such-supplier/reference-images",
        headers=_auth_headers(),
    )
    assert r.status_code == 404
    assert r.json().get("code") == CLIENT_SUPPLIER_NOT_FOUND


def test_list_supplier_reference_images_supplier_not_under_client() -> None:
    c_other = _create_client("Other client")
    c_wrong = _create_client("Wrong scoped client")
    sid_on_other = _create_supplier(c_other)
    r = client.get(
        f"/api/v3/clients/{c_wrong}/suppliers/{sid_on_other}/reference-images",
        headers=_auth_headers(),
    )
    assert r.status_code == 409
    assert r.json().get("code") == CLIENT_SUPPLIER_CLIENT_MISMATCH


def test_upload_supplier_reference_images_success_multi_and_optional_metadata() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    r = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
        files=[
            ("files", ("one.jpg", BytesIO(b"a"), "image/jpeg")),
            ("files", ("two.png", BytesIO(b"b"), "image/png")),
        ],
        data={"label": "  Etiqueta  ", "description": "  Desc  "},
        headers=_auth_headers(),
    )
    assert r.status_code == 201
    items = r.json()["items"]
    assert len(items) == 2
    assert items[0]["label"] == "Etiqueta"
    assert items[0]["description"] == "Desc"
    assert items[1]["label"] == "Etiqueta"
    assert all("storage_path" not in it for it in items)


def test_upload_supplier_reference_images_missing_client() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    r = client.post(
        f"/api/v3/clients/missing/suppliers/{sid}/reference-images",
        files=[("files", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    assert r.status_code == 404
    assert r.json().get("code") == CLIENT_NOT_FOUND


def test_upload_supplier_reference_images_supplier_wrong_client() -> None:
    c_owner = _create_client("Owner")
    c_other = _create_client("Other")
    sid = _create_supplier(c_owner)
    r = client.post(
        f"/api/v3/clients/{c_other}/suppliers/{sid}/reference-images",
        files=[("files", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    assert r.status_code == 409
    assert r.json().get("code") == CLIENT_SUPPLIER_CLIENT_MISMATCH


def test_upload_supplier_reference_images_unsupported_mime() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    r = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
        files=[("files", ("x.pdf", BytesIO(b"p"), "application/pdf"))],
        headers=_auth_headers(),
    )
    assert r.status_code == 400
    assert r.json().get("code") == UNSUPPORTED_ASSET_TYPE


def test_upload_supplier_reference_images_zero_byte() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    r = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
        files=[("files", ("empty.jpg", BytesIO(b""), "image/jpeg"))],
        headers=_auth_headers(),
    )
    assert r.status_code == 422
    detail = str(r.json().get("detail", "")).lower()
    assert "zero-byte" in detail or "empty" in detail


def test_delete_supplier_reference_image_returns_contract_shape() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    up = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
        files=[("files", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    image_id = up.json()["items"][0]["id"]
    r = client.delete(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images/{image_id}",
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    assert r.json() == {"deleted": True, "id": image_id}


def test_delete_supplier_reference_image_missing_returns_structured_404() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    r = client.delete(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images/no-such-id",
        headers=_auth_headers(),
    )
    assert r.status_code == 404
    assert r.json().get("code") == SUPPLIER_REFERENCE_IMAGE_NOT_FOUND


def test_delete_supplier_reference_image_wrong_supplier_same_client() -> None:
    cid = _create_client()
    s1 = _create_supplier(cid, "S1")
    s2 = _create_supplier(cid, "S2")
    up = client.post(
        f"/api/v3/clients/{cid}/suppliers/{s1}/reference-images",
        files=[("files", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    image_id = up.json()["items"][0]["id"]
    r = client.delete(
        f"/api/v3/clients/{cid}/suppliers/{s2}/reference-images/{image_id}",
        headers=_auth_headers(),
    )
    assert r.status_code == 404
    assert r.json().get("code") == SUPPLIER_REFERENCE_IMAGE_NOT_FOUND


def test_delete_supplier_reference_image_wrong_client() -> None:
    c1 = _create_client("C1")
    c2 = _create_client("C2")
    sid = _create_supplier(c1)
    up = client.post(
        f"/api/v3/clients/{c1}/suppliers/{sid}/reference-images",
        files=[("files", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    image_id = up.json()["items"][0]["id"]
    r = client.delete(
        f"/api/v3/clients/{c2}/suppliers/{sid}/reference-images/{image_id}",
        headers=_auth_headers(),
    )
    assert r.status_code == 409
    assert r.json().get("code") == CLIENT_SUPPLIER_CLIENT_MISMATCH


def test_supplier_reference_image_file_redirect_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("ARTIFACT_S3_BUCKET", "bucket-x")
    monkeypatch.setenv("ARTIFACT_S3_SIGNED_URL_TTL_SEC", "777")
    # Do not call reload_settings() here: dotenv reload can undo monkeypatched ARTIFACT_* / OUTPUT_DIR.
    config_module._settings = AppSettings()
    reset_app_container_for_tests()
    app.dependency_overrides[get_artifact_storage] = lambda: StubSignedUrlArtifactStorage()
    try:
        cid = _create_client()
        sid = _create_supplier(cid)
        upload_resp = client.post(
            f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
            files=[("files", ("ref.jpg", BytesIO(b"jpeg-data"), "image/jpeg"))],
            headers=_auth_headers(),
        )
        assert upload_resp.status_code == 201
        image_id = client.get(
            f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
            headers=_auth_headers(),
        ).json()["items"][0]["id"]

        file_resp = client.get(
            f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images/{image_id}/file",
            headers=_auth_headers(),
            follow_redirects=False,
        )
        assert file_resp.status_code == 307
        assert file_resp.headers["location"].startswith("https://signed.example/client_suppliers/")
        assert "exp=777" in file_resp.headers["location"]
    finally:
        app.dependency_overrides.pop(get_artifact_storage, None)
        monkeypatch.delenv("ARTIFACT_STORAGE_PROVIDER", raising=False)
        monkeypatch.delenv("ARTIFACT_S3_BUCKET", raising=False)
        monkeypatch.delenv("ARTIFACT_S3_SIGNED_URL_TTL_SEC", raising=False)
        reload_settings()
        reset_app_container_for_tests()


def test_supplier_reference_image_file_legacy_local_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED", "true")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    config_module._settings = AppSettings()
    reset_app_container_for_tests()
    cid = _create_client()
    sid = _create_supplier(cid)
    upload_resp = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images",
        files=[("files", ("ref.jpg", BytesIO(b"jpeg-data"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    assert upload_resp.status_code == 201
    image_id = upload_resp.json()["items"][0]["id"]

    rel = supplier_reference_image_storage_path(sid, image_id, "image/jpeg")
    p = tmp_path / "v3_uploads" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"legacy-supplier-bytes")

    try:
        file_resp = client.get(
            f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images/{image_id}/file",
            headers=_auth_headers(),
        )
        assert file_resp.status_code == 200
        assert file_resp.content == b"legacy-supplier-bytes"
        assert file_resp.headers.get("content-type", "").startswith("image/jpeg")
    finally:
        monkeypatch.delenv("ARTIFACT_STORAGE_PROVIDER", raising=False)
        monkeypatch.delenv("ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED", raising=False)
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        reload_settings()
        reset_app_container_for_tests()


def test_supplier_reference_image_file_missing_image() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    r = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/reference-images/missing-id/file",
        headers=_auth_headers(),
    )
    assert r.status_code == 404
    assert r.json().get("code") == SUPPLIER_REFERENCE_IMAGE_NOT_FOUND


def test_supplier_reference_image_file_wrong_supplier_rejected() -> None:
    cid = _create_client()
    s1 = _create_supplier(cid, "S1")
    s2 = _create_supplier(cid, "S2")
    client.post(
        f"/api/v3/clients/{cid}/suppliers/{s1}/reference-images",
        files=[("files", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    image_id = client.get(
        f"/api/v3/clients/{cid}/suppliers/{s1}/reference-images",
        headers=_auth_headers(),
    ).json()["items"][0]["id"]
    r = client.get(
        f"/api/v3/clients/{cid}/suppliers/{s2}/reference-images/{image_id}/file",
        headers=_auth_headers(),
    )
    assert r.status_code == 404
    assert r.json().get("code") == SUPPLIER_REFERENCE_IMAGE_NOT_FOUND


def test_supplier_reference_image_file_cross_client_rejected() -> None:
    c1 = _create_client("C1")
    c2 = _create_client("C2")
    sid = _create_supplier(c1)
    client.post(
        f"/api/v3/clients/{c1}/suppliers/{sid}/reference-images",
        files=[("files", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
        headers=_auth_headers(),
    )
    image_id = client.get(
        f"/api/v3/clients/{c1}/suppliers/{sid}/reference-images",
        headers=_auth_headers(),
    ).json()["items"][0]["id"]
    r = client.get(
        f"/api/v3/clients/{c2}/suppliers/{sid}/reference-images/{image_id}/file",
        headers=_auth_headers(),
    )
    assert r.status_code == 409
    assert r.json().get("code") == CLIENT_SUPPLIER_CLIENT_MISMATCH
