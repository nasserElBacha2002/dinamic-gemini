"""G6 — preview from materialized SourceAssets for an assigned temporal group."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from src.application.errors import (
    CaptureSessionGroupNotAssignedForPreviewError,
    CaptureSessionGroupNotMaterializedForPreviewError,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.capture_sessions.compute_materialized_capture_session_group_preview import (
    ComputeMaterializedCaptureSessionGroupPreviewUseCase,
    _classify_g6_preview_status,
    _G6PreviewStatusInputs,
)
from src.application.use_cases.capture_sessions.materialize_capture_session_group import (
    MaterializeCaptureSessionGroupUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
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
    Image.new("RGB", (4, 4), color=(10, 20, 30)).save(bio, format="JPEG", quality=85)
    return bio.getvalue()


def _base_ctx(tmp_path):
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    group_repo = MemoryCaptureSessionGroupRepository(item_repo)
    asset_repo = MemorySourceAssetRepository()
    position_repo = MemoryPositionRepository()
    store = V3ArtifactStorageAdapter(tmp_path)
    clock = _FixedClock(datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc))
    reconciler = InventoryStatusReconciler(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        clock=clock,
    )
    mat_uc = MaterializeCaptureSessionGroupUseCase(
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
        preview_max_positions=50,
    )
    inv_id = str(uuid4())
    aisle_id = str(uuid4())
    session_id = str(uuid4())
    group_id = str(uuid4())
    other_group_id = str(uuid4())
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
            code="G6-A1",
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
    return {
        "mat_uc": mat_uc,
        "preview_uc": preview_uc,
        "inv_id": inv_id,
        "aisle_id": aisle_id,
        "session_id": session_id,
        "group_id": group_id,
        "other_group_id": other_group_id,
        "item_repo": item_repo,
        "group_repo": group_repo,
        "asset_repo": asset_repo,
        "position_repo": position_repo,
        "store": store,
        "clock": clock,
    }


def _insert_assigned_group(c, *, group_id: str | None = None) -> str:
    gid = group_id or c["group_id"]
    now = c["clock"].now()
    c["group_repo"].insert(
        CaptureSessionGroup(
            id=gid,
            session_id=c["session_id"],
            group_index=1,
            created_at=now,
            algorithm_version="time_gap_v1",
            assigned_aisle_id=c["aisle_id"],
            assignment_status=CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_EXISTING,
            assigned_at=now,
        )
    )
    return gid


def test_classify_g6_preview_status_explicit_contract() -> None:
    assert (
        _classify_g6_preview_status(
            _G6PreviewStatusInputs(
                filtered_asset_count=0,
                resolved_row_count=0,
                distinct_preview_imported_item_count=0,
                has_any_unlinked_imported_in_group=False,
                proposed_outcome_count=0,
                conflict_outcome_count=0,
                unassigned_outcome_count=0,
            )
        )
        == "empty"
    )
    assert (
        _classify_g6_preview_status(
            _G6PreviewStatusInputs(
                filtered_asset_count=2,
                resolved_row_count=0,
                distinct_preview_imported_item_count=0,
                has_any_unlinked_imported_in_group=False,
                proposed_outcome_count=0,
                conflict_outcome_count=0,
                unassigned_outcome_count=0,
            )
        )
        == "empty"
    )
    assert (
        _classify_g6_preview_status(
            _G6PreviewStatusInputs(
                filtered_asset_count=1,
                resolved_row_count=1,
                distinct_preview_imported_item_count=1,
                has_any_unlinked_imported_in_group=False,
                proposed_outcome_count=1,
                conflict_outcome_count=0,
                unassigned_outcome_count=0,
            )
        )
        == "ready"
    )
    assert (
        _classify_g6_preview_status(
            _G6PreviewStatusInputs(
                filtered_asset_count=2,
                resolved_row_count=1,
                distinct_preview_imported_item_count=1,
                has_any_unlinked_imported_in_group=False,
                proposed_outcome_count=1,
                conflict_outcome_count=0,
                unassigned_outcome_count=0,
            )
        )
        == "partial"
    )
    assert (
        _classify_g6_preview_status(
            _G6PreviewStatusInputs(
                filtered_asset_count=1,
                resolved_row_count=1,
                distinct_preview_imported_item_count=1,
                has_any_unlinked_imported_in_group=True,
                proposed_outcome_count=1,
                conflict_outcome_count=0,
                unassigned_outcome_count=0,
            )
        )
        == "partial"
    )
    assert (
        _classify_g6_preview_status(
            _G6PreviewStatusInputs(
                filtered_asset_count=1,
                resolved_row_count=1,
                distinct_preview_imported_item_count=1,
                has_any_unlinked_imported_in_group=False,
                proposed_outcome_count=0,
                conflict_outcome_count=1,
                unassigned_outcome_count=0,
            )
        )
        == "partial"
    )
    assert (
        _classify_g6_preview_status(
            _G6PreviewStatusInputs(
                filtered_asset_count=1,
                resolved_row_count=1,
                distinct_preview_imported_item_count=1,
                has_any_unlinked_imported_in_group=False,
                proposed_outcome_count=0,
                conflict_outcome_count=0,
                unassigned_outcome_count=1,
            )
        )
        == "partial"
    )
    assert (
        _classify_g6_preview_status(
            _G6PreviewStatusInputs(
                filtered_asset_count=1,
                resolved_row_count=1,
                distinct_preview_imported_item_count=2,
                has_any_unlinked_imported_in_group=False,
                proposed_outcome_count=1,
                conflict_outcome_count=0,
                unassigned_outcome_count=0,
            )
        )
        == "partial"
    )


def test_preview_metadata_scoped_asset_without_resolvable_item_is_empty_and_stable(
    tmp_path,
) -> None:
    """Metadata matches session+group but no joinable item → no rows; trace count stays on filtered assets."""
    c = _base_ctx(tmp_path)
    now = c["clock"].now()
    _insert_assigned_group(c)
    orphan_id = str(uuid4())
    c["asset_repo"].save(
        SourceAsset(
            id=orphan_id,
            aisle_id=c["aisle_id"],
            type=SourceAssetType.PHOTO,
            original_filename="orphan.jpg",
            storage_path="orphan",
            mime_type="image/jpeg",
            uploaded_at=now,
            metadata_json={
                "capture_session_id": c["session_id"],
                "capture_session_group_id": c["group_id"],
            },
            capture_session_item_id=None,
        )
    )
    out = c["preview_uc"].execute(
        inventory_id=c["inv_id"],
        session_id=c["session_id"],
        group_id=c["group_id"],
    )
    out2 = c["preview_uc"].execute(
        inventory_id=c["inv_id"],
        session_id=c["session_id"],
        group_id=c["group_id"],
    )
    assert out == out2
    assert out.source_asset_count == 1
    assert out.source_asset_ids == (orphan_id,)
    assert out.preview_status == "empty"
    assert out.preview_operator_state == out.preview_status
    assert out.items == ()


def test_preview_unassigned_group_raises(tmp_path) -> None:
    c = _base_ctx(tmp_path)
    now = c["clock"].now()
    c["group_repo"].insert(
        CaptureSessionGroup(
            id=c["group_id"],
            session_id=c["session_id"],
            group_index=1,
            created_at=now,
            algorithm_version="time_gap_v1",
            assignment_status=CaptureSessionGroupAisleAssignmentStatus.UNASSIGNED,
        )
    )
    with pytest.raises(CaptureSessionGroupNotAssignedForPreviewError):
        c["preview_uc"].execute(
            inventory_id=c["inv_id"],
            session_id=c["session_id"],
            group_id=c["group_id"],
        )


def test_preview_assigned_not_materialized_raises(tmp_path) -> None:
    c = _base_ctx(tmp_path)
    now = c["clock"].now()
    _insert_assigned_group(c)
    key = "staging/s1.bin"
    (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / key).write_bytes(_tiny_jpeg_bytes())
    c["item_repo"].save(
        CaptureSessionItem(
            id=str(uuid4()),
            session_id=c["session_id"],
            staging_storage_key=key,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="a.jpg",
            group_id=c["group_id"],
        )
    )
    with pytest.raises(CaptureSessionGroupNotMaterializedForPreviewError):
        c["preview_uc"].execute(
            inventory_id=c["inv_id"],
            session_id=c["session_id"],
            group_id=c["group_id"],
        )


def test_preview_assigned_materialized_succeeds(tmp_path) -> None:
    c = _base_ctx(tmp_path)
    now = c["clock"].now()
    item1_id, item2_id = str(uuid4()), str(uuid4())
    key1, key2 = "staging/s1.bin", "staging/s2.bin"
    (tmp_path / key1).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / key1).write_bytes(_tiny_jpeg_bytes())
    (tmp_path / key2).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / key2).write_bytes(_tiny_jpeg_bytes())
    c["item_repo"].save(
        CaptureSessionItem(
            id=item1_id,
            session_id=c["session_id"],
            staging_storage_key=key1,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="a.jpg",
            group_id=c["group_id"],
        )
    )
    c["item_repo"].save(
        CaptureSessionItem(
            id=item2_id,
            session_id=c["session_id"],
            staging_storage_key=key2,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now + timedelta(seconds=5),
            original_filename="b.jpg",
            group_id=c["group_id"],
        )
    )
    _insert_assigned_group(c)
    for idx, code in enumerate(["Z-A", "Z-B"]):
        c["position_repo"].save(
            Position(
                id=str(uuid4()),
                aisle_id=c["aisle_id"],
                status=PositionStatus.DETECTED,
                confidence=1.0,
                needs_review=True,
                primary_evidence_id=None,
                created_at=now,
                updated_at=now,
                corrected_position_code=code,
            )
        )
    c["mat_uc"].materialize_one(
        inventory_id=c["inv_id"], session_id=c["session_id"], group_id=c["group_id"]
    )
    r1 = c["preview_uc"].execute(
        inventory_id=c["inv_id"],
        session_id=c["session_id"],
        group_id=c["group_id"],
    )
    r2 = c["preview_uc"].execute(
        inventory_id=c["inv_id"],
        session_id=c["session_id"],
        group_id=c["group_id"],
    )
    assert r1 == r2
    assert r1.preview_status == "ready"
    assert r1.preview_operator_state == r1.preview_status
    assert r1.source_asset_count == 2
    assert len(r1.source_asset_ids) == 2
    assert r1.aisle_id == c["aisle_id"]
    assert r1.capture_session_id == c["session_id"]
    assert {i.source_asset_id for i in r1.items} == set(r1.source_asset_ids)
    assert r1.summary.proposed_count == 2


def test_preview_filters_other_group_assets_on_same_aisle(tmp_path) -> None:
    c = _base_ctx(tmp_path)
    now = c["clock"].now()
    _insert_assigned_group(c, group_id=c["group_id"])
    _insert_assigned_group(c, group_id=c["other_group_id"])
    key = "staging/s1.bin"
    (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / key).write_bytes(_tiny_jpeg_bytes())
    item_a = str(uuid4())
    c["item_repo"].save(
        CaptureSessionItem(
            id=item_a,
            session_id=c["session_id"],
            staging_storage_key=key,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="a.jpg",
            group_id=c["group_id"],
        )
    )
    c["mat_uc"].materialize_one(
        inventory_id=c["inv_id"], session_id=c["session_id"], group_id=c["group_id"]
    )

    noise_id = str(uuid4())
    c["asset_repo"].save(
        SourceAsset(
            id=noise_id,
            aisle_id=c["aisle_id"],
            type=SourceAssetType.PHOTO,
            original_filename="noise.jpg",
            storage_path="x",
            mime_type="image/jpeg",
            uploaded_at=now,
            metadata_json={
                "capture_session_id": c["session_id"],
                "capture_session_group_id": c["other_group_id"],
                "capture_session_item_id": str(uuid4()),
            },
            capture_session_item_id=str(uuid4()),
        )
    )

    c["position_repo"].save(
        Position(
            id=str(uuid4()),
            aisle_id=c["aisle_id"],
            status=PositionStatus.DETECTED,
            confidence=1.0,
            needs_review=True,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            corrected_position_code="P1",
        )
    )
    out = c["preview_uc"].execute(
        inventory_id=c["inv_id"],
        session_id=c["session_id"],
        group_id=c["group_id"],
    )
    assert noise_id not in out.source_asset_ids
    assert out.source_asset_count == 1


def test_preview_empty_when_materialized_only_non_imported_items(tmp_path) -> None:
    c = _base_ctx(tmp_path)
    now = c["clock"].now()
    _insert_assigned_group(c)
    key = "staging/s1.bin"
    (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / key).write_bytes(_tiny_jpeg_bytes())
    item_id = str(uuid4())
    c["item_repo"].save(
        CaptureSessionItem(
            id=item_id,
            session_id=c["session_id"],
            staging_storage_key=key,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="a.jpg",
            group_id=c["group_id"],
        )
    )
    c["mat_uc"].materialize_one(
        inventory_id=c["inv_id"], session_id=c["session_id"], group_id=c["group_id"]
    )
    row = c["item_repo"].get_by_id(item_id)
    assert row is not None
    row.import_status = CaptureSessionItemImportStatus.IMPORT_FAILED
    c["item_repo"].save(row)
    out = c["preview_uc"].execute(
        inventory_id=c["inv_id"],
        session_id=c["session_id"],
        group_id=c["group_id"],
    )
    assert out.preview_status == "empty"
    assert out.preview_operator_state == out.preview_status
    assert out.source_asset_count == 1


def test_preview_partial_when_materialization_incomplete(tmp_path) -> None:
    c = _base_ctx(tmp_path)
    now = c["clock"].now()
    _insert_assigned_group(c)
    key1, key2 = "staging/s1.bin", "staging/s2.bin"
    (tmp_path / key1).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / key1).write_bytes(_tiny_jpeg_bytes())
    (tmp_path / key2).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / key2).write_bytes(_tiny_jpeg_bytes())
    i1, i2 = str(uuid4()), str(uuid4())
    c["item_repo"].save(
        CaptureSessionItem(
            id=i1,
            session_id=c["session_id"],
            staging_storage_key=key1,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="a.jpg",
            group_id=c["group_id"],
        )
    )
    c["item_repo"].save(
        CaptureSessionItem(
            id=i2,
            session_id=c["session_id"],
            staging_storage_key=key2,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now + timedelta(seconds=2),
            original_filename="b.jpg",
            group_id=c["group_id"],
        )
    )
    c["mat_uc"].materialize_one(
        inventory_id=c["inv_id"], session_id=c["session_id"], group_id=c["group_id"]
    )
    c["position_repo"].save(
        Position(
            id=str(uuid4()),
            aisle_id=c["aisle_id"],
            status=PositionStatus.DETECTED,
            confidence=1.0,
            needs_review=True,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            corrected_position_code="P1",
        )
    )
    c["item_repo"].save(
        CaptureSessionItem(
            id=i2,
            session_id=c["session_id"],
            staging_storage_key=key2,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now + timedelta(seconds=2),
            original_filename="b.jpg",
            group_id=c["group_id"],
            linked_source_asset_id="",
        )
    )
    out = c["preview_uc"].execute(
        inventory_id=c["inv_id"],
        session_id=c["session_id"],
        group_id=c["group_id"],
    )
    assert out.preview_status == "partial"
    assert out.preview_operator_state == out.preview_status
    assert out.source_asset_count >= 1
