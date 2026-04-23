"""API tests: v3 capture sessions (Sprint 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_artifact_storage
from src.api.server import app
from src.api.errors.structured_api_http import (
    CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
    CAPTURE_SESSION_NOT_FOUND,
    CAPTURE_SESSION_INVALID_STATE,
    CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS,
    CAPTURE_SESSION_STATUS_FILTER_INVALID,
    OPEN_CAPTURE_SESSION_EXISTS,
)
from src.infrastructure.repositories.memory_capture_session_group_repository import (
    MemoryCaptureSessionGroupRepository,
)
from src.infrastructure.repositories.memory_capture_session_item_repository import MemoryCaptureSessionItemRepository
from src.infrastructure.repositories.memory_capture_session_repository import MemoryCaptureSessionRepository
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from src.runtime.app_container import reset_app_container_for_tests
from src.runtime.v3_deps import (
    get_capture_session_group_repo,
    get_capture_session_item_repo,
    get_capture_session_repo,
)

client = TestClient(app)


@pytest.fixture
def memory_capture(tmp_path: Path):
    reset_app_container_for_tests()
    sr = MemoryCaptureSessionRepository()
    ir = MemoryCaptureSessionItemRepository()
    gr = MemoryCaptureSessionGroupRepository(ir)
    store = V3ArtifactStorageAdapter(tmp_path / "v3_uploads")
    app.dependency_overrides[get_capture_session_repo] = lambda: sr
    app.dependency_overrides[get_capture_session_item_repo] = lambda: ir
    app.dependency_overrides[get_capture_session_group_repo] = lambda: gr
    app.dependency_overrides[get_artifact_storage] = lambda: store
    yield
    app.dependency_overrides.pop(get_capture_session_repo, None)
    app.dependency_overrides.pop(get_capture_session_item_repo, None)
    app.dependency_overrides.pop(get_capture_session_group_repo, None)
    app.dependency_overrides.pop(get_artifact_storage, None)
    reset_app_container_for_tests()


def _create_inv_aisle() -> tuple[str, str]:
    r = client.post("/api/v3/inventories", json={"name": "Cap Inv"})
    assert r.status_code == 201, r.text
    inv_id = r.json()["id"]
    r2 = client.post(f"/api/v3/inventories/{inv_id}/aisles", json={"code": "C-01"})
    assert r2.status_code == 201, r2.text
    return inv_id, r2.json()["id"]


def test_create_list_detail_upload_flow(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    cr = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions")
    assert cr.status_code == 201, cr.text
    session_id = cr.json()["id"]
    lr = client.get(f"/api/v3/inventories/{inv_id}/capture-sessions")
    assert lr.status_code == 200
    body = lr.json()
    assert body["total_items"] == 1
    assert len(body["items"]) == 1
    dr = client.get(f"/api/v3/inventories/{inv_id}/capture-sessions/{session_id}")
    assert dr.status_code == 200
    assert dr.json()["session"]["id"] == session_id
    assets_before = client.get(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets")
    assert assets_before.status_code == 200
    assert assets_before.json() == []
    up = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items",
        files=[("files", ("x.jpg", b"abc", "image/jpeg"))],
    )
    assert up.status_code == 201, up.text
    payload = up.json()
    assert payload["errors"] == []
    items = payload["items"]
    assert len(items) == 1
    assert items[0]["import_status"] == "imported"
    assert items[0]["staging_storage_key"].startswith("capture/staging/")
    assets_after = client.get(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets")
    assert assets_after.status_code == 200
    assert assets_after.json() == []


def test_create_inventory_level_session_without_aisle(memory_capture: None) -> None:
    inv_id, _aisle_id = _create_inv_aisle()
    cr = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions")
    assert cr.status_code == 201, cr.text
    body = cr.json()
    assert body["inventory_id"] == inv_id
    assert body["aisle_id"] is None
    lr = client.get(f"/api/v3/inventories/{inv_id}/capture-sessions")
    assert lr.status_code == 200
    assert lr.json()["total_items"] == 1
    assert lr.json()["items"][0]["aisle_id"] is None


def test_inventory_level_upload_close_cancel_flow(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions").json()["id"]
    up = client.post(
        f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/items",
        files=[("files", ("inv-level.jpg", b"inv-level-bytes", "image/jpeg"))],
    )
    assert up.status_code == 201, up.text
    assert up.json()["items"][0]["import_status"] == "imported"

    close_resp = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/close")
    assert close_resp.status_code == 200, close_resp.text
    assert close_resp.json()["session"]["status"] == "ready_for_review"

    cancel_resp = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/cancel")
    assert cancel_resp.status_code == 200, cancel_resp.text
    assert cancel_resp.json()["session"]["status"] == "cancelled"

    # Legacy aisle-scoped flow remains valid in mixed environment.
    legacy_sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()["id"]
    legacy_up = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{legacy_sid}/items",
        files=[("files", ("legacy.jpg", b"legacy-bytes", "image/jpeg"))],
    )
    assert legacy_up.status_code == 201, legacy_up.text
    mixed = client.get(f"/api/v3/inventories/{inv_id}/capture-sessions")
    assert mixed.status_code == 200
    assert mixed.json()["total_items"] == 2
    aisle_values = {row["aisle_id"] for row in mixed.json()["items"]}
    assert aisle_id in aisle_values
    assert None in aisle_values


def test_open_session_conflict_returns_409(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    assert client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").status_code == 201
    r2 = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions")
    assert r2.status_code == 409
    assert r2.json()["code"] == OPEN_CAPTURE_SESSION_EXISTS


def test_cancel_blocks_upload(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()["id"]
    assert (
        client.post(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/cancel"
        ).status_code
        == 200
    )
    up = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/items",
        files=[("files", ("x.jpg", b"z", "image/jpeg"))],
    )
    assert up.status_code == 409
    assert up.json()["code"] == CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS


def test_duplicate_files_in_single_request_partial_success(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()["id"]
    body = b"dup-in-batch"
    r = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/items",
        files=[
            ("files", ("a.jpg", body, "image/jpeg")),
            ("files", ("b.jpg", body, "image/jpeg")),
        ],
    )
    assert r.status_code == 201, r.text
    payload = r.json()
    assert len(payload["items"]) == 1
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["code"] == "CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT"
    assert payload["errors"][0]["file_index"] == 1


def test_duplicate_upload_content_returns_per_file_error(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()["id"]
    body = b"same-payload"
    assert (
        client.post(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/items",
            files=[("files", ("a.jpg", body, "image/jpeg"))],
        ).status_code
        == 201
    )
    r2 = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/items",
        files=[("files", ("b.jpg", body, "image/jpeg"))],
    )
    assert r2.status_code == 201, r2.text
    body2 = r2.json()
    assert body2["items"] == []
    assert len(body2["errors"]) == 1
    assert body2["errors"][0]["code"] == "CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT"


def test_close_session_success(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()["id"]
    up = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/items",
        files=[("files", ("x.jpg", b"data", "image/jpeg"))],
    )
    assert up.status_code == 201, up.text
    r = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/close",
    )
    assert r.status_code == 200
    assert r.json()["session"]["status"] == "ready_for_review"
    assert r.json()["session"]["closed_at"] is not None


def test_close_empty_draft_returns_409(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()["id"]
    r = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/close")
    assert r.status_code == 409
    assert r.json()["code"] == CAPTURE_SESSION_INVALID_STATE


def test_list_invalid_status_filter_returns_422(memory_capture: None) -> None:
    inv_id, _ = _create_inv_aisle()
    r = client.get(f"/api/v3/inventories/{inv_id}/capture-sessions?status=not_a_real_status")
    assert r.status_code == 422
    assert r.json()["code"] == CAPTURE_SESSION_STATUS_FILTER_INVALID


def test_list_status_filter_empty_segment_returns_422(memory_capture: None) -> None:
    inv_id, _ = _create_inv_aisle()
    r = client.get(f"/api/v3/inventories/{inv_id}/capture-sessions?status=draft,")
    assert r.status_code == 422
    assert r.json()["code"] == CAPTURE_SESSION_STATUS_FILTER_INVALID


def test_list_valid_status_filter_ok(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions")
    r = client.get(f"/api/v3/inventories/{inv_id}/capture-sessions?status=draft")
    assert r.status_code == 200
    assert r.json()["total_items"] == 1


def test_inventory_level_preview_path_returns_structured_not_found(memory_capture: None) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions").json()["id"]
    r = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/preview-assignment"
    )
    assert r.status_code == 404
    assert r.json()["code"] == CAPTURE_SESSION_NOT_FOUND


def test_compute_groups_before_close_returns_409(memory_capture: None) -> None:
    inv_id, _aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions").json()["id"]
    up = client.post(
        f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/items",
        files=[("files", ("x.jpg", b"bytes-for-grouping", "image/jpeg"))],
    )
    assert up.status_code == 201, up.text
    r = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/compute-groups")
    assert r.status_code == 409, r.text
    assert r.json()["code"] == CAPTURE_SESSION_GROUPING_NOT_ALLOWED


def test_compute_groups_after_close_and_list_groups(memory_capture: None) -> None:
    inv_id, _aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions").json()["id"]
    up = client.post(
        f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/items",
        files=[("files", ("a.jpg", b"a-bytes", "image/jpeg"))],
    )
    assert up.status_code == 201, up.text
    assert client.post(f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/close").status_code == 200

    cg = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/compute-groups")
    assert cg.status_code == 200, cg.text
    body = cg.json()
    assert "groups" in body
    assert len(body["groups"]) >= 1
    g0 = body["groups"][0]
    assert g0["group_index"] == 1
    assert g0["item_count"] >= 1
    assert g0["group_id"]
    assert g0["start_time"]
    assert g0["end_time"]
    assert g0["algorithm_version"] == "time_gap_v1"

    lg = client.get(f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/groups")
    assert lg.status_code == 200, lg.text
    assert lg.json()["groups"] == body["groups"]

    detail = client.get(f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}")
    assert detail.status_code == 200
    items = detail.json()["items"]
    assert any(i.get("group_id") == g0["group_id"] for i in items)

    cg2 = client.post(f"/api/v3/inventories/{inv_id}/capture-sessions/{sid}/compute-groups")
    assert cg2.status_code == 200, cg2.text
    assert len(cg2.json()["groups"]) == len(body["groups"])
