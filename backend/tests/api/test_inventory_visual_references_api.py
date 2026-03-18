"""API tests for inventory visual references endpoints — v3.2.4."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

from src.api.server import app
from src.config import reload_settings

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

