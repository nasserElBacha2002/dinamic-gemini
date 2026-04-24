"""API tests: Phase 4 materialize capture session endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_artifact_storage
from src.api.errors.structured_api_http import (
    CAPTURE_SESSION_ALREADY_MATERIALIZED,
    CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED,
)
from src.api.server import app
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_capture_session_confirm_idempotency_repository import (
    MemoryCaptureSessionConfirmIdempotencyRepository,
)
from src.infrastructure.repositories.memory_capture_session_group_repository import (
    MemoryCaptureSessionGroupRepository,
)
from src.infrastructure.repositories.memory_capture_session_item_repository import MemoryCaptureSessionItemRepository
from src.infrastructure.repositories.memory_capture_session_repository import MemoryCaptureSessionRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_source_asset_repository import MemorySourceAssetRepository
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from src.runtime.app_container import reset_app_container_for_tests
from src.runtime.v3_deps import (
    get_capture_session_confirm_repo,
    get_capture_session_group_repo,
    get_capture_session_item_repo,
    get_capture_session_repo,
    get_position_repo,
    get_source_asset_repo,
)

client = TestClient(app)


@pytest.fixture
def materialize_capture_ctx(tmp_path: Path):
    reset_app_container_for_tests()
    sr = MemoryCaptureSessionRepository()
    ir = MemoryCaptureSessionItemRepository()
    gr = MemoryCaptureSessionGroupRepository(ir)
    pr = MemoryPositionRepository()
    ar = MemorySourceAssetRepository()
    cr = MemoryCaptureSessionConfirmIdempotencyRepository()
    store = V3ArtifactStorageAdapter(tmp_path / "v3_uploads")
    app.dependency_overrides[get_capture_session_repo] = lambda: sr
    app.dependency_overrides[get_capture_session_item_repo] = lambda: ir
    app.dependency_overrides[get_position_repo] = lambda: pr
    app.dependency_overrides[get_source_asset_repo] = lambda: ar
    app.dependency_overrides[get_capture_session_confirm_repo] = lambda: cr
    app.dependency_overrides[get_artifact_storage] = lambda: store
    yield {"position_repo": pr, "asset_repo": ar}
    app.dependency_overrides.pop(get_capture_session_repo, None)
    app.dependency_overrides.pop(get_capture_session_item_repo, None)
    app.dependency_overrides.pop(get_capture_session_group_repo, None)
    app.dependency_overrides.pop(get_position_repo, None)
    app.dependency_overrides.pop(get_source_asset_repo, None)
    app.dependency_overrides.pop(get_capture_session_confirm_repo, None)
    app.dependency_overrides.pop(get_artifact_storage, None)
    reset_app_container_for_tests()


def _create_inv_aisle() -> tuple[str, str]:
    r = client.post("/api/v3/inventories", json={"name": "Cap materialize"})
    assert r.status_code == 201, r.text
    inv_id = r.json()["id"]
    r2 = client.post(f"/api/v3/inventories/{inv_id}/aisles", json={"code": "M-01"})
    assert r2.status_code == 201, r2.text
    return inv_id, r2.json()["id"]


def _build_assignment_proposed_session(inv_id: str, aisle_id: str, position_repo: MemoryPositionRepository) -> str:
    t = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    position_repo.save(
        Position(
            id="pos-api-m1",
            aisle_id=aisle_id,
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=t,
            updated_at=t,
            corrected_position_code="A1",
        )
    )
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()["id"]
    up = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/items",
        files=[("files", ("a.jpg", b"payload-materialize", "image/jpeg"))],
    )
    assert up.status_code == 201, up.text
    assert (
        client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/close").status_code == 200
    )
    pv = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/preview-assignment")
    assert pv.status_code == 200, pv.text
    return sid


def test_materialize_happy_path_and_retry_same_key(materialize_capture_ctx) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = _build_assignment_proposed_session(inv_id, aisle_id, materialize_capture_ctx["position_repo"])
    first = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/materialize",
        json={"idempotency_key": "k-1"},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["session"]["status"] == "confirming"
    assert body["created_assets_count"] == 1
    assert body["items"][0]["linked_source_asset_id"]
    assets = list(materialize_capture_ctx["asset_repo"].list_by_aisle(aisle_id))
    assert len(assets) == 1
    meta = assets[0].metadata_json or {}
    assert meta["capture_session_id"] == sid
    assert meta["capture_session_item_id"] == body["items"][0]["id"]
    assert "effective_capture_time" in meta
    assert "time_source" in meta
    assert "assignment_reason" in meta
    assert "preview_target_position_id" in meta
    second = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/materialize",
        json={"idempotency_key": "k-1"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["created_assets_count"] == 1
    assert len(materialize_capture_ctx["asset_repo"].list_by_aisle(aisle_id)) == 1


def test_materialize_different_key_after_success_returns_conflict(materialize_capture_ctx) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = _build_assignment_proposed_session(inv_id, aisle_id, materialize_capture_ctx["position_repo"])
    assert (
        client.post(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/materialize",
            json={"idempotency_key": "k-a"},
        ).status_code
        == 200
    )
    r = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/materialize",
        json={"idempotency_key": "k-b"},
    )
    assert r.status_code == 409
    assert r.json()["code"] == CAPTURE_SESSION_ALREADY_MATERIALIZED


def test_materialize_missing_or_invalid_idempotency_key(materialize_capture_ctx) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = _build_assignment_proposed_session(inv_id, aisle_id, materialize_capture_ctx["position_repo"])
    missing = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/materialize", json={})
    assert missing.status_code == 422
    blank = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/materialize",
        json={"idempotency_key": ""},
    )
    assert blank.status_code == 422


def test_materialize_invalid_session_state(materialize_capture_ctx) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()["id"]
    r = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/materialize",
        json={"idempotency_key": "nope"},
    )
    assert r.status_code == 409
    assert r.json()["code"] == CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED
