"""G7 — observability, integrity, retry safety, and operator-facing summaries."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from src.application.errors import CaptureSessionGroupIntegrityError
from src.application.services.capture_flow_observability import get_capture_flow_metrics
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.compute_materialized_capture_session_group_preview import (
    ComputeMaterializedCaptureSessionGroupPreviewUseCase,
)
from src.application.use_cases.materialize_capture_session_group import (
    MaterializeCaptureSessionGroupUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionGroup,
    CaptureSessionGroupAisleAssignmentStatus,
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_capture_session_group_repository import (
    MemoryCaptureSessionGroupRepository,
)
from src.infrastructure.repositories.memory_capture_session_item_repository import (
    MemoryCaptureSessionItemRepository,
)
from src.infrastructure.repositories.memory_capture_session_repository import (
    MemoryCaptureSessionRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter


class _FixedClock:
    def __init__(self, t: datetime) -> None:
        self._t = t

    def now(self) -> datetime:
        return self._t


def _tiny_jpeg_bytes() -> bytes:
    bio = BytesIO()
    Image.new("RGB", (4, 4), color=(1, 2, 3)).save(bio, format="JPEG", quality=85)
    return bio.getvalue()


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    get_capture_flow_metrics().reset_for_tests()
    yield
    get_capture_flow_metrics().reset_for_tests()


def test_materialize_retry_stable_and_emits_structured_log(caplog, tmp_path) -> None:
    caplog.set_level(logging.INFO)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    group_repo = MemoryCaptureSessionGroupRepository(item_repo)
    asset_repo = MemorySourceAssetRepository()
    store = V3ArtifactStorageAdapter(tmp_path)
    clock = _FixedClock(datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc))
    reconciler = InventoryStatusReconciler(
        inventory_repo=inv_repo, aisle_repo=aisle_repo, clock=clock
    )
    uc = MaterializeCaptureSessionGroupUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        item_repo=item_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=store,
        status_reconciler=reconciler,
        clock=clock,
    )
    inv_id, aisle_id, session_id, group_id = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    now = clock.now()
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code="G7-A",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    session_repo.save(
        CaptureSession(
            id=session_id,
            inventory_id=inv_id,
            aisle_id=None,
            status=CaptureSessionStatus.READY_FOR_REVIEW,
            created_at=now,
            updated_at=now,
            closed_at=now,
        )
    )
    key = "staging/g7.jpg"
    (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / key).write_bytes(_tiny_jpeg_bytes())
    item_id = str(uuid4())
    item_repo.save(
        CaptureSessionItem(
            id=item_id,
            session_id=session_id,
            staging_storage_key=key,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="g7.jpg",
            group_id=group_id,
        )
    )
    group_repo.insert(
        CaptureSessionGroup(
            id=group_id,
            session_id=session_id,
            group_index=1,
            created_at=now,
            algorithm_version="time_gap_v1",
            assigned_aisle_id=aisle_id,
            assignment_status=CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_EXISTING,
            assigned_at=now,
        )
    )
    uc.materialize_one(inventory_id=inv_id, session_id=session_id, group_id=group_id)
    uc.materialize_one(inventory_id=inv_id, session_id=session_id, group_id=group_id)
    assert len(asset_repo.list_by_aisle(aisle_id)) == 1
    g7_logs = [r for r in caplog.records if "G5_materialize_group" in r.getMessage()]
    assert len(g7_logs) >= 2
    payloads = [json.loads(r.getMessage()) for r in g7_logs]
    assert all(p.get("operation") == "G5_materialize_group" for p in payloads)
    assert all(
        p.get("inventory_id") == inv_id and p.get("session_id") == session_id for p in payloads
    )
    assert get_capture_flow_metrics().materializations_total >= 2


def test_preview_partial_after_partial_materialization(tmp_path) -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    group_repo = MemoryCaptureSessionGroupRepository(item_repo)
    asset_repo = MemorySourceAssetRepository()
    position_repo = MemoryPositionRepository()
    store = V3ArtifactStorageAdapter(tmp_path)
    clock = _FixedClock(datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc))
    reconciler = InventoryStatusReconciler(
        inventory_repo=inv_repo, aisle_repo=aisle_repo, clock=clock
    )
    mat = MaterializeCaptureSessionGroupUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        item_repo=item_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=store,
        status_reconciler=reconciler,
        clock=clock,
    )
    preview_uc = ComputeMaterializedCaptureSessionGroupPreviewUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        item_repo=item_repo,
        position_repo=position_repo,
        asset_repo=asset_repo,
        preview_max_positions=10,
    )
    inv_id, aisle_id, session_id, group_id = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    now = clock.now()
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code="G7-B",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    session_repo.save(
        CaptureSession(
            id=session_id,
            inventory_id=inv_id,
            aisle_id=None,
            status=CaptureSessionStatus.READY_FOR_REVIEW,
            created_at=now,
            updated_at=now,
            closed_at=now,
            clock_offset_seconds=0,
        )
    )
    group_repo.insert(
        CaptureSessionGroup(
            id=group_id,
            session_id=session_id,
            group_index=1,
            created_at=now,
            algorithm_version="time_gap_v1",
            assigned_aisle_id=aisle_id,
            assignment_status=CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_EXISTING,
            assigned_at=now,
        )
    )
    key1, key2 = "staging/a.jpg", "staging/b.jpg"
    for k in (key1, key2):
        (tmp_path / k).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / k).write_bytes(_tiny_jpeg_bytes())
    i1, i2 = str(uuid4()), str(uuid4())
    item_repo.save(
        CaptureSessionItem(
            id=i1,
            session_id=session_id,
            staging_storage_key=key1,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="a.jpg",
            group_id=group_id,
        )
    )
    item_repo.save(
        CaptureSessionItem(
            id=i2,
            session_id=session_id,
            staging_storage_key=key2,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="b.jpg",
            group_id=group_id,
        )
    )
    pos_id = str(uuid4())
    position_repo.save(
        Position(
            id=pos_id,
            aisle_id=aisle_id,
            status=PositionStatus.DETECTED,
            confidence=1.0,
            needs_review=True,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            corrected_position_code="Z-1",
        )
    )
    mat.materialize_one(inventory_id=inv_id, session_id=session_id, group_id=group_id)
    it2 = item_repo.get_by_id(i2)
    assert it2 is not None
    it2.linked_source_asset_id = None
    it2.updated_at = now
    item_repo.save(it2)

    out = preview_uc.execute(inventory_id=inv_id, session_id=session_id, group_id=group_id)
    assert out.preview_status == "partial"
    assert out.preview_operator_state == "partial"


def test_group_summary_materialization_state_partial() -> None:
    item_repo = MemoryCaptureSessionItemRepository()
    group_repo = MemoryCaptureSessionGroupRepository(item_repo)
    _inv_id, aisle_id, session_id, group_id = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
    item_repo.save(
        CaptureSessionItem(
            id=str(uuid4()),
            session_id=session_id,
            staging_storage_key="k1",
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            group_id=group_id,
            linked_source_asset_id=str(uuid4()),
        )
    )
    item_repo.save(
        CaptureSessionItem(
            id=str(uuid4()),
            session_id=session_id,
            staging_storage_key="k2",
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            group_id=group_id,
            linked_source_asset_id=None,
        )
    )
    group_repo.insert(
        CaptureSessionGroup(
            id=group_id,
            session_id=session_id,
            group_index=1,
            created_at=now,
            algorithm_version="time_gap_v1",
            assigned_aisle_id=aisle_id,
            assignment_status=CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_EXISTING,
            assigned_at=now,
        )
    )
    summaries = group_repo.list_summaries(session_id)
    assert len(summaries) == 1
    assert summaries[0].materialization_state == "partially_materialized"


def test_validate_group_items_coherent_rejects_wrong_group() -> None:
    from src.application.services.capture_group_item_integrity import validate_group_items_coherent

    sid, gid = str(uuid4()), str(uuid4())
    bad = CaptureSessionItem(
        id=str(uuid4()),
        session_id=sid,
        staging_storage_key="k",
        import_status=CaptureSessionItemImportStatus.IMPORTED,
        assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
        updated_at=datetime.now(timezone.utc),
        effective_capture_time=datetime.now(timezone.utc),
        group_id="other-group",
    )
    with pytest.raises(CaptureSessionGroupIntegrityError):
        validate_group_items_coherent([bad], session_id=sid, group_id=gid)
