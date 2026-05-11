"""API tests: Sprint 3 capture session clock offset + assignment preview."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_artifact_storage
from src.api.errors.structured_api_http import (
    CAPTURE_SESSION_INVALID_CLOCK_OFFSET,
    CAPTURE_SESSION_PREVIEW_NOT_ALLOWED,
)
from src.api.server import app
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_capture_session_group_repository import (
    MemoryCaptureSessionGroupRepository,
)
from src.infrastructure.repositories.memory_capture_session_item_repository import (
    MemoryCaptureSessionItemRepository,
)
from src.infrastructure.repositories.memory_capture_session_repository import (
    MemoryCaptureSessionRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from src.runtime.app_container import reset_app_container_for_tests
from src.runtime.v3_deps import (
    get_capture_session_group_repo,
    get_capture_session_item_repo,
    get_capture_session_repo,
    get_position_repo,
)
from tests.support.api_v3_test_helpers import create_test_inventory

client = TestClient(app)


@pytest.fixture
def memory_capture_s3(tmp_path: Path):
    reset_app_container_for_tests()
    sr = MemoryCaptureSessionRepository()
    ir = MemoryCaptureSessionItemRepository()
    gr = MemoryCaptureSessionGroupRepository(ir)
    pr = MemoryPositionRepository()
    store = V3ArtifactStorageAdapter(tmp_path / "v3_uploads")
    app.dependency_overrides[get_capture_session_repo] = lambda: sr
    app.dependency_overrides[get_capture_session_item_repo] = lambda: ir
    app.dependency_overrides[get_capture_session_group_repo] = lambda: gr
    app.dependency_overrides[get_position_repo] = lambda: pr
    app.dependency_overrides[get_artifact_storage] = lambda: store
    yield pr
    app.dependency_overrides.pop(get_capture_session_repo, None)
    app.dependency_overrides.pop(get_capture_session_item_repo, None)
    app.dependency_overrides.pop(get_capture_session_group_repo, None)
    app.dependency_overrides.pop(get_position_repo, None)
    app.dependency_overrides.pop(get_artifact_storage, None)
    reset_app_container_for_tests()


def _create_inv_aisle() -> tuple[str, str]:
    r = create_test_inventory(client, name="Cap S3")
    assert r.status_code == 201, r.text
    inv_id = r.json()["id"]
    r2 = client.post(f"/api/v3/inventories/{inv_id}/aisles", json={"code": "S3-01"})
    assert r2.status_code == 201, r2.text
    return inv_id, r2.json()["id"]


def test_patch_clock_offset_and_preview_flow(memory_capture_s3: MemoryPositionRepository) -> None:
    from datetime import datetime, timezone

    inv_id, aisle_id = _create_inv_aisle()
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    memory_capture_s3.save(
        Position(
            id="pos-api-1",
            aisle_id=aisle_id,
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=t,
            updated_at=t,
            corrected_position_code="R1",
        )
    )
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()[
        "id"
    ]
    up = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/items",
        files=[("files", ("a.jpg", b"payload-s3-unique", "image/jpeg"))],
    )
    assert up.status_code == 201, up.text
    assert up.json()["items"][0].get("effective_capture_time") is not None
    assert (
        client.post(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/close",
        ).status_code
        == 200
    )
    pr = client.patch(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/clock-offset",
        json={"clock_offset_seconds": 120},
    )
    assert pr.status_code == 200, pr.text
    assert pr.json()["session"]["clock_offset_seconds"] == 120
    pv = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/preview-assignment",
    )
    assert pv.status_code == 200, pv.text
    assert pv.json()["session"]["status"] == "assignment_proposed"
    it0 = pv.json()["items"][0]
    assert it0["assignment_status"] == "proposed"
    assert it0.get("preview_target_position_id") == "pos-api-1"
    assert it0.get("adjusted_capture_time") is not None


def test_preview_before_close_409(memory_capture_s3: MemoryPositionRepository) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()[
        "id"
    ]
    assert (
        client.post(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/items",
            files=[("files", ("a.jpg", b"x", "image/jpeg"))],
        ).status_code
        == 201
    )
    r = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/preview-assignment",
    )
    assert r.status_code == 409
    assert r.json()["code"] == CAPTURE_SESSION_PREVIEW_NOT_ALLOWED


def test_invalid_clock_offset_422(memory_capture_s3: MemoryPositionRepository) -> None:
    inv_id, aisle_id = _create_inv_aisle()
    sid = client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions").json()[
        "id"
    ]
    r = client.patch(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/capture-sessions/{sid}/clock-offset",
        json={"clock_offset_seconds": 99999999},
    )
    assert r.status_code == 422
    assert r.json()["code"] == CAPTURE_SESSION_INVALID_CLOCK_OFFSET
