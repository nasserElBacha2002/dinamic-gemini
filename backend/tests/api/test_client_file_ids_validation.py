"""client_file_ids / upload_batch_id validation on multipart upload endpoints (aisle assets)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_artifact_storage
from src.api.errors.structured_api_http import (
    CLIENT_FILE_ID_INVALID,
    CLIENT_FILE_IDS_MISMATCH,
    UPLOAD_BATCH_ID_INVALID,
)
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from tests.support.api_v3_test_helpers import create_test_inventory, create_test_supplier

_VALID_UUID_1 = "11111111-1111-1111-1111-111111111111"
_VALID_UUID_2 = "22222222-2222-2222-2222-222222222222"


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


def _create_inventory_and_aisle(client_v3: TestClient, code: str) -> tuple[str, str]:
    create = create_test_inventory(client_v3, name=f"ClientFileIds {code}")
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


def test_client_file_ids_length_mismatch_returns_422(client_v3: TestClient) -> None:
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CFI-01")

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[
            ("files", ("a.jpg", b"fake_jpeg_a", "image/jpeg")),
            ("files", ("b.jpg", b"fake_jpeg_b", "image/jpeg")),
        ],
        data={"client_file_ids": _VALID_UUID_1},
    )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == CLIENT_FILE_IDS_MISMATCH


def test_client_file_ids_matching_count_of_valid_uuids_is_accepted(client_v3: TestClient) -> None:
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CFI-02")

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[
            ("files", ("a.jpg", b"fake_jpeg_a", "image/jpeg")),
            ("files", ("b.jpg", b"fake_jpeg_b", "image/jpeg")),
        ],
        data={"client_file_ids": [_VALID_UUID_1, _VALID_UUID_2]},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    client_ids = {item["client_file_id"] for item in body["uploaded"]}
    assert client_ids == {_VALID_UUID_1, _VALID_UUID_2}


def test_missing_client_file_ids_is_legacy_compatible(client_v3: TestClient) -> None:
    """No client_file_ids at all is still allowed (all files map to client_file_id=None)."""
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CFI-03")

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[("files", ("a.jpg", b"fake_jpeg_a", "image/jpeg"))],
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["uploaded"][0]["client_file_id"] is None


def test_client_file_id_not_uuid_shaped_returns_422(client_v3: TestClient) -> None:
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CFI-04")

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[("files", ("a.jpg", b"fake_jpeg_a", "image/jpeg"))],
        data={"client_file_ids": "not-a-uuid"},
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == CLIENT_FILE_ID_INVALID


def test_client_file_id_over_max_length_returns_422(client_v3: TestClient) -> None:
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CFI-05")
    too_long = "a" * 65

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[("files", ("a.jpg", b"fake_jpeg_a", "image/jpeg"))],
        data={"client_file_ids": too_long},
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == CLIENT_FILE_ID_INVALID


def test_upload_batch_id_not_uuid_shaped_returns_422(client_v3: TestClient) -> None:
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CFI-06")

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[("files", ("a.jpg", b"fake_jpeg_a", "image/jpeg"))],
        data={"upload_batch_id": "not-a-uuid"},
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == UPLOAD_BATCH_ID_INVALID


def test_valid_upload_batch_id_is_accepted(client_v3: TestClient) -> None:
    inv_id, aisle_id = _create_inventory_and_aisle(client_v3, "CFI-07")

    resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[("files", ("a.jpg", b"fake_jpeg_a", "image/jpeg"))],
        data={"upload_batch_id": _VALID_UUID_1},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["batch_id"] == _VALID_UUID_1
