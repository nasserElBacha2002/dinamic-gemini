"""API-level enforcement of max files per upload request."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.constants.error_wire import HTTP_DETAIL_TOO_MANY_FILES_PER_UPLOAD
from src.api.errors.structured_api_http import UPLOAD_TOO_MANY_FILES_PER_REQUEST
from src.api.server import app
from src.application.constants.upload_limits import MAX_FILES_PER_UPLOAD_REQUEST
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from tests.support.api_v3_test_helpers import create_test_inventory, create_test_supplier


@pytest.fixture
def client_v3() -> TestClient:
    def _fake_admin() -> AuthUser:
        return AuthUser(id="admin", username="admin", role="administrator")

    app.dependency_overrides[get_current_admin] = _fake_admin
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_aisle_assets_upload_rejects_over_max_files(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Upload Limit")
    assert create.status_code == 201
    inv_id = create.json()["id"]
    inv = client_v3.get(f"/api/v3/inventories/{inv_id}").json()
    sid = create_test_supplier(client_v3, inv["client_id"])
    aisle_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "UL-01", "client_supplier_id": sid},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    over_limit = MAX_FILES_PER_UPLOAD_REQUEST + 1
    files = [("files", (f"f{i}.jpg", b"x", "image/jpeg")) for i in range(over_limit)]
    response = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=files,
    )
    assert response.status_code == 400
    body = response.json()
    assert body.get("code") == UPLOAD_TOO_MANY_FILES_PER_REQUEST
    assert body.get("detail") == HTTP_DETAIL_TOO_MANY_FILES_PER_UPLOAD


def test_aisle_assets_upload_accepts_max_files(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Upload Limit OK")
    assert create.status_code == 201
    inv_id = create.json()["id"]
    inv = client_v3.get(f"/api/v3/inventories/{inv_id}").json()
    sid = create_test_supplier(client_v3, inv["client_id"])
    aisle_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "UL-10", "client_supplier_id": sid},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    files = [
        ("files", (f"f{i}.jpg", b"fake_jpeg_content", "image/jpeg"))
        for i in range(MAX_FILES_PER_UPLOAD_REQUEST)
    ]
    response = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=files,
    )
    assert response.status_code == 201
    assert len(response.json()["assets"]) == MAX_FILES_PER_UPLOAD_REQUEST


def _create_aisle(client_v3: TestClient, inv_id: str) -> str:
    inv = client_v3.get(f"/api/v3/inventories/{inv_id}").json()
    sid = create_test_supplier(client_v3, inv["client_id"])
    aisle_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "CAP-UL", "client_supplier_id": sid},
    )
    assert aisle_resp.status_code == 201
    return aisle_resp.json()["id"]


def test_capture_session_items_inventory_scope_rejects_over_max_files(
    client_v3: TestClient,
) -> None:
    create = create_test_inventory(client_v3, name="Capture Upload Limit Inv")
    assert create.status_code == 201
    inv_id = create.json()["id"]
    session_resp = client_v3.post(f"/api/v3/inventories/{inv_id}/capture-sessions")
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    over_limit = MAX_FILES_PER_UPLOAD_REQUEST + 1
    files = [("files", (f"f{i}.jpg", b"x", "image/jpeg")) for i in range(over_limit)]
    response = client_v3.post(
        f"/api/v3/inventories/{inv_id}/capture-sessions/{session_id}/items",
        files=files,
    )
    assert response.status_code == 400
    body = response.json()
    assert body.get("code") == UPLOAD_TOO_MANY_FILES_PER_REQUEST
    assert body.get("detail") == HTTP_DETAIL_TOO_MANY_FILES_PER_UPLOAD


def test_capture_session_items_inventory_scope_accepts_max_files(
    client_v3: TestClient,
) -> None:
    create = create_test_inventory(client_v3, name="Capture Upload OK Inv")
    assert create.status_code == 201
    inv_id = create.json()["id"]
    session_resp = client_v3.post(f"/api/v3/inventories/{inv_id}/capture-sessions")
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    files = [
        ("files", (f"f{i}.jpg", b"fake_jpeg_content", "image/jpeg"))
        for i in range(MAX_FILES_PER_UPLOAD_REQUEST)
    ]
    response = client_v3.post(
        f"/api/v3/inventories/{inv_id}/capture-sessions/{session_id}/items",
        files=files,
    )
    assert response.status_code == 201
    assert response.json().get("code") != UPLOAD_TOO_MANY_FILES_PER_REQUEST


def test_capture_session_items_aisle_scope_rejects_over_max_files(
    client_v3: TestClient,
) -> None:
    create = create_test_inventory(client_v3, name="Capture Upload Limit Aisle")
    assert create.status_code == 201
    inv_id = create.json()["id"]
    aisle_id = _create_aisle(client_v3, inv_id)
    session_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions"
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    over_limit = MAX_FILES_PER_UPLOAD_REQUEST + 1
    files = [("files", (f"f{i}.jpg", b"x", "image/jpeg")) for i in range(over_limit)]
    response = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items",
        files=files,
    )
    assert response.status_code == 400
    body = response.json()
    assert body.get("code") == UPLOAD_TOO_MANY_FILES_PER_REQUEST
    assert body.get("detail") == HTTP_DETAIL_TOO_MANY_FILES_PER_UPLOAD


def test_capture_session_items_aisle_scope_accepts_max_files(
    client_v3: TestClient,
) -> None:
    create = create_test_inventory(client_v3, name="Capture Upload OK Aisle")
    assert create.status_code == 201
    inv_id = create.json()["id"]
    aisle_id = _create_aisle(client_v3, inv_id)
    session_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions"
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    files = [
        ("files", (f"f{i}.jpg", f"payload-unique-{i}".encode(), "image/jpeg"))
        for i in range(MAX_FILES_PER_UPLOAD_REQUEST)
    ]
    response = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items",
        files=files,
    )
    assert response.status_code == 201
    assert len(response.json()["items"]) == MAX_FILES_PER_UPLOAD_REQUEST
