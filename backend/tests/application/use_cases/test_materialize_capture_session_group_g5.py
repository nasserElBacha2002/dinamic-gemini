"""G5 — materialize assigned capture session groups to aisle SourceAssets."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from src.application.errors import CaptureSessionGroupNotAssignedForMaterializationError
from src.application.ports.clock import Clock
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.materialize_capture_session_group import MaterializeCaptureSessionGroupUseCase
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
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_capture_session_group_repository import MemoryCaptureSessionGroupRepository
from src.infrastructure.repositories.memory_capture_session_item_repository import MemoryCaptureSessionItemRepository
from src.infrastructure.repositories.memory_capture_session_repository import MemoryCaptureSessionRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_source_asset_repository import MemorySourceAssetRepository
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter


class _FixedClock(Clock):
    def __init__(self, t: datetime) -> None:
        self._t = t

    def now(self) -> datetime:
        return self._t


def _tiny_jpeg_bytes() -> bytes:
    bio = BytesIO()
    Image.new("RGB", (4, 4), color=(10, 20, 30)).save(bio, format="JPEG", quality=85)
    return bio.getvalue()


def _ctx(tmp_path):
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    group_repo = MemoryCaptureSessionGroupRepository(item_repo)
    asset_repo = MemorySourceAssetRepository()
    store = V3ArtifactStorageAdapter(tmp_path)
    clock = _FixedClock(datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc))
    reconciler = InventoryStatusReconciler(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        clock=clock,
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
    inv_id = str(uuid4())
    aisle_id = str(uuid4())
    session_id = str(uuid4())
    group_id = str(uuid4())
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
            code="G5-A1",
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
        "uc": uc,
        "inv_id": inv_id,
        "aisle_id": aisle_id,
        "session_id": session_id,
        "group_id": group_id,
        "item_repo": item_repo,
        "group_repo": group_repo,
        "asset_repo": asset_repo,
        "store": store,
        "clock": clock,
    }


def test_materialize_assigned_group_creates_assets_and_traceability(tmp_path) -> None:
    c = _ctx(tmp_path)
    uc = c["uc"]
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
            effective_capture_time=now,
            original_filename="b.jpg",
            group_id=c["group_id"],
        )
    )
    c["group_repo"].insert(
        CaptureSessionGroup(
            id=c["group_id"],
            session_id=c["session_id"],
            group_index=1,
            created_at=now,
            algorithm_version="time_gap_v1",
            assigned_aisle_id=c["aisle_id"],
            assignment_status=CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_EXISTING,
            assigned_at=now,
        )
    )

    out = uc.materialize_one(inventory_id=c["inv_id"], session_id=c["session_id"], group_id=c["group_id"])
    assert out.created_assets == 2
    assert out.skipped_assets == 0
    assert out.failed_assets == 0
    a1 = c["asset_repo"].get_by_capture_session_item_id(item1_id)
    assert a1 is not None
    assert a1.aisle_id == c["aisle_id"]
    assert a1.capture_session_item_id == item1_id
    meta = a1.metadata_json or {}
    assert meta.get("capture_session_id") == c["session_id"]
    assert meta.get("capture_session_group_id") == c["group_id"]
    assert meta.get("capture_session_item_id") == item1_id
    assert meta.get("original_filename") == "a.jpg"


def test_materialize_idempotent_second_run_skips(tmp_path) -> None:
    c = _ctx(tmp_path)
    uc = c["uc"]
    now = c["clock"].now()
    item_id = str(uuid4())
    key = "staging/one.jpg"
    (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / key).write_bytes(_tiny_jpeg_bytes())
    c["item_repo"].save(
        CaptureSessionItem(
            id=item_id,
            session_id=c["session_id"],
            staging_storage_key=key,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="x.jpg",
            group_id=c["group_id"],
        )
    )
    c["group_repo"].insert(
        CaptureSessionGroup(
            id=c["group_id"],
            session_id=c["session_id"],
            group_index=1,
            created_at=now,
            algorithm_version="time_gap_v1",
            assigned_aisle_id=c["aisle_id"],
            assignment_status=CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_EXISTING,
            assigned_at=now,
        )
    )
    r1 = uc.materialize_one(inventory_id=c["inv_id"], session_id=c["session_id"], group_id=c["group_id"])
    assert r1.created_assets == 1
    r2 = uc.materialize_one(inventory_id=c["inv_id"], session_id=c["session_id"], group_id=c["group_id"])
    assert r2.created_assets == 0
    assert r2.skipped_assets == 1
    assert len(c["asset_repo"].list_by_aisle(c["aisle_id"])) == 1


def test_unassigned_group_raises(tmp_path) -> None:
    c = _ctx(tmp_path)
    uc = c["uc"]
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
    with pytest.raises(CaptureSessionGroupNotAssignedForMaterializationError):
        uc.materialize_one(inventory_id=c["inv_id"], session_id=c["session_id"], group_id=c["group_id"])


def test_partial_failure_one_item_other_succeeds(tmp_path) -> None:
    c = _ctx(tmp_path)
    uc = c["uc"]
    now = c["clock"].now()
    good_id, bad_id = "it-good-aaa", "it-bad-zzz"
    good_key = "staging/good.jpg"
    (tmp_path / good_key).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / good_key).write_bytes(_tiny_jpeg_bytes())
    c["item_repo"].save(
        CaptureSessionItem(
            id=good_id,
            session_id=c["session_id"],
            staging_storage_key=good_key,
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="g.jpg",
            group_id=c["group_id"],
        )
    )
    c["item_repo"].save(
        CaptureSessionItem(
            id=bad_id,
            session_id=c["session_id"],
            staging_storage_key="staging/missing.jpg",
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=now,
            effective_capture_time=now,
            original_filename="bad.jpg",
            group_id=c["group_id"],
        )
    )
    c["group_repo"].insert(
        CaptureSessionGroup(
            id=c["group_id"],
            session_id=c["session_id"],
            group_index=1,
            created_at=now,
            algorithm_version="time_gap_v1",
            assigned_aisle_id=c["aisle_id"],
            assignment_status=CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_EXISTING,
            assigned_at=now,
        )
    )
    out = uc.materialize_one(inventory_id=c["inv_id"], session_id=c["session_id"], group_id=c["group_id"])
    assert out.created_assets == 1
    assert out.failed_assets == 1
    assert c["asset_repo"].get_by_capture_session_item_id(good_id) is not None
