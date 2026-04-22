"""Phase 4: materialize capture session staging items into SourceAsset rows."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

import pytest

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import (
    CaptureSessionAlreadyMaterializedError,
    CaptureSessionInvalidIdempotencyKeyError,
    CaptureSessionMaterializationFailedError,
    CaptureSessionMaterializationNotAllowedError,
)
from src.application.ports.clock import Clock
from src.application.services.capture_staging_time_metadata import PillowCaptureStagingTimeMetadataExtractor
from src.application.use_cases.close_capture_session import CloseCaptureSessionUseCase
from src.application.use_cases.compute_capture_session_assignment_preview import (
    ComputeCaptureSessionAssignmentPreviewUseCase,
)
from src.application.use_cases.create_capture_session import CreateCaptureSessionUseCase
from src.application.use_cases.materialize_capture_session import MaterializeCaptureSessionUseCase
from src.application.use_cases.upload_capture_session_staging_items import UploadCaptureSessionStagingItemsUseCase
from src.domain.capture.entities import CaptureSessionItemAssignmentStatus, CaptureSessionStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_capture_session_confirm_idempotency_repository import (
    MemoryCaptureSessionConfirmIdempotencyRepository,
)
from src.infrastructure.repositories.memory_capture_session_item_repository import MemoryCaptureSessionItemRepository
from src.infrastructure.repositories.memory_capture_session_repository import MemoryCaptureSessionRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_source_asset_repository import MemorySourceAssetRepository
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler


class _FixedClock(Clock):
    def __init__(self, t: datetime) -> None:
        self._t = t

    def now(self) -> datetime:
        return self._t


def _pillow_time_extractor() -> PillowCaptureStagingTimeMetadataExtractor:
    return PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=0.85,
        confidence_mtime=0.55,
        confidence_fallback=0.35,
    )


def _seed_inv_aisle():
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inv_id = str(uuid4())
    aisle_id = str(uuid4())
    now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    from src.domain.aisle.entities import Aisle, AisleStatus
    from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus

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
            code="A-1",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    return inv_repo, aisle_repo, inv_id, aisle_id


def _prepare_assignment_proposed_session(tmp_path):
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    pos_repo = MemoryPositionRepository()
    asset_repo = MemorySourceAssetRepository()
    confirm_repo = MemoryCaptureSessionConfirmIdempotencyRepository()
    store = V3ArtifactStorageAdapter(tmp_path)
    clock = _FixedClock(datetime(2026, 5, 1, 13, 0, 0, tzinfo=timezone.utc))
    pos_repo.save(
        Position(
            id="pos-1",
            aisle_id=aisle_id,
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=clock.now(),
            updated_at=clock.now(),
            corrected_position_code="A1",
        )
    )
    session = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=3,
    ).execute(inv_id, aisle_id)
    UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=store,
        clock=clock,
        staging_prefix="capture/staging",
        max_files_per_upload=10,
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    ).execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=session.id,
        files=[UploadedFile("a.jpg", BytesIO(b"materialize-me"), "image/jpeg")],
    )
    CloseCaptureSessionUseCase(session_repo=session_repo, item_repo=item_repo, clock=clock).execute(
        inventory_id=inv_id, aisle_id=aisle_id, session_id=session.id
    )
    ComputeCaptureSessionAssignmentPreviewUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        position_repo=pos_repo,
        clock=clock,
        preview_max_positions=100,
    ).execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=session.id)
    return {
        "inv_repo": inv_repo,
        "aisle_repo": aisle_repo,
        "inv_id": inv_id,
        "aisle_id": aisle_id,
        "session_id": session.id,
        "session_repo": session_repo,
        "item_repo": item_repo,
        "asset_repo": asset_repo,
        "confirm_repo": confirm_repo,
        "store": store,
        "clock": clock,
    }


def _materialize_uc(ctx) -> MaterializeCaptureSessionUseCase:
    return MaterializeCaptureSessionUseCase(
        session_repo=ctx["session_repo"],
        item_repo=ctx["item_repo"],
        confirm_repo=ctx["confirm_repo"],
        aisle_repo=ctx["aisle_repo"],
        asset_repo=ctx["asset_repo"],
        artifact_storage=ctx["store"],
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=ctx["inv_repo"],
            aisle_repo=ctx["aisle_repo"],
            clock=ctx["clock"],
        ),
        clock=ctx["clock"],
    )


def test_materialize_success_creates_source_assets_links_items_and_sets_confirming(tmp_path) -> None:
    ctx = _prepare_assignment_proposed_session(tmp_path)
    out = _materialize_uc(ctx).execute(
        inventory_id=ctx["inv_id"],
        aisle_id=ctx["aisle_id"],
        session_id=ctx["session_id"],
        idempotency_key="m-key-1",
    )
    assert out.replayed is False
    assert len(out.created_asset_ids) == 1
    session = ctx["session_repo"].get_by_id(ctx["session_id"])
    assert session is not None
    assert session.status == CaptureSessionStatus.CONFIRMING
    items = list(ctx["item_repo"].list_by_session(ctx["session_id"]))
    assert items[0].linked_source_asset_id == out.created_asset_ids[0]
    assets = list(ctx["asset_repo"].list_by_aisle(ctx["aisle_id"]))
    assert [a.id for a in assets] == list(out.created_asset_ids)
    meta = assets[0].metadata_json or {}
    assert meta["capture_session_id"] == ctx["session_id"]
    assert meta["capture_session_item_id"] == items[0].id
    assert meta["time_source"] is not None
    assert "effective_capture_time" in meta
    assert "assignment_reason" in meta
    assert "preview_target_position_id" in meta


def test_materialize_same_idempotency_key_replays_without_duplicates(tmp_path) -> None:
    ctx = _prepare_assignment_proposed_session(tmp_path)
    uc = _materialize_uc(ctx)
    first = uc.execute(
        inventory_id=ctx["inv_id"],
        aisle_id=ctx["aisle_id"],
        session_id=ctx["session_id"],
        idempotency_key="idem-42",
    )
    second = uc.execute(
        inventory_id=ctx["inv_id"],
        aisle_id=ctx["aisle_id"],
        session_id=ctx["session_id"],
        idempotency_key="idem-42",
    )
    assert second.replayed is True
    assert second.created_asset_ids == first.created_asset_ids
    assert len(ctx["asset_repo"].list_by_aisle(ctx["aisle_id"])) == 1


def test_materialize_different_idempotency_key_after_success_is_blocked(tmp_path) -> None:
    ctx = _prepare_assignment_proposed_session(tmp_path)
    uc = _materialize_uc(ctx)
    uc.execute(
        inventory_id=ctx["inv_id"],
        aisle_id=ctx["aisle_id"],
        session_id=ctx["session_id"],
        idempotency_key="idem-a",
    )
    with pytest.raises(CaptureSessionAlreadyMaterializedError):
        uc.execute(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            session_id=ctx["session_id"],
            idempotency_key="idem-b",
        )


def test_materialize_rejects_invalid_session_state(tmp_path) -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    session = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=_FixedClock(datetime(2026, 5, 1, 13, 0, 0, tzinfo=timezone.utc)),
        max_open_sessions_per_aisle=3,
    ).execute(inv_id, aisle_id)
    uc = MaterializeCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=MemoryCaptureSessionItemRepository(),
        confirm_repo=MemoryCaptureSessionConfirmIdempotencyRepository(),
        aisle_repo=aisle_repo,
        asset_repo=MemorySourceAssetRepository(),
        artifact_storage=V3ArtifactStorageAdapter(tmp_path),
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inv_repo,
            aisle_repo=aisle_repo,
            clock=_FixedClock(datetime(2026, 5, 1, 13, 0, 0, tzinfo=timezone.utc)),
        ),
        clock=_FixedClock(datetime(2026, 5, 1, 13, 0, 0, tzinfo=timezone.utc)),
    )
    with pytest.raises(CaptureSessionMaterializationNotAllowedError):
        uc.execute(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            session_id=session.id,
            idempotency_key="key",
        )


def test_materialize_rejects_when_imported_item_is_not_proposed(tmp_path) -> None:
    ctx = _prepare_assignment_proposed_session(tmp_path)
    item = list(ctx["item_repo"].list_by_session(ctx["session_id"]))[0]
    item.assignment_status = CaptureSessionItemAssignmentStatus.UNASSIGNED
    ctx["item_repo"].save(item)
    with pytest.raises(CaptureSessionMaterializationNotAllowedError):
        _materialize_uc(ctx).execute(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            session_id=ctx["session_id"],
            idempotency_key="idem-x",
        )


def test_materialize_failure_rolls_back_links_and_assets(tmp_path) -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    pos_repo = MemoryPositionRepository()
    asset_repo = MemorySourceAssetRepository()
    confirm_repo = MemoryCaptureSessionConfirmIdempotencyRepository()
    store = V3ArtifactStorageAdapter(tmp_path)
    clock = _FixedClock(datetime(2026, 5, 1, 13, 0, 0, tzinfo=timezone.utc))
    for idx in (1, 2):
        pos_repo.save(
            Position(
                id=f"pos-{idx}",
                aisle_id=aisle_id,
                status=PositionStatus.DETECTED,
                confidence=0.9,
                needs_review=False,
                primary_evidence_id=None,
                created_at=clock.now(),
                updated_at=clock.now(),
                corrected_position_code=f"A{idx}",
            )
        )
    session = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=3,
    ).execute(inv_id, aisle_id)
    UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=store,
        clock=clock,
        staging_prefix="capture/staging",
        max_files_per_upload=10,
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    ).execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=session.id,
        files=[
            UploadedFile(
                "a.jpg",
                BytesIO(b"roll-1"),
                "image/jpeg",
                last_modified_at=datetime(2026, 5, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            UploadedFile(
                "b.jpg",
                BytesIO(b"roll-2"),
                "image/jpeg",
                last_modified_at=datetime(2026, 5, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
        ],
    )
    CloseCaptureSessionUseCase(session_repo=session_repo, item_repo=item_repo, clock=clock).execute(
        inventory_id=inv_id, aisle_id=aisle_id, session_id=session.id
    )
    ComputeCaptureSessionAssignmentPreviewUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        position_repo=pos_repo,
        clock=clock,
        preview_max_positions=100,
    ).execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=session.id)
    items = list(item_repo.list_by_session(session.id))
    items[1].staging_storage_key = "capture/staging/missing-object.jpg"
    item_repo.save(items[1])
    uc = MaterializeCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        confirm_repo=confirm_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=store,
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inv_repo,
            aisle_repo=aisle_repo,
            clock=clock,
        ),
        clock=clock,
    )
    with pytest.raises(CaptureSessionMaterializationFailedError):
        uc.execute(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            session_id=session.id,
            idempotency_key="rollback-1",
        )
    assert len(asset_repo.list_by_aisle(aisle_id)) == 0
    after = list(item_repo.list_by_session(session.id))
    assert all(i.linked_source_asset_id is None for i in after)
    sess_after = session_repo.get_by_id(session.id)
    assert sess_after is not None
    assert sess_after.status == CaptureSessionStatus.ASSIGNMENT_PROPOSED


def test_materialize_missing_idempotency_key_rejected_with_domain_error(tmp_path) -> None:
    ctx = _prepare_assignment_proposed_session(tmp_path)
    with pytest.raises(CaptureSessionInvalidIdempotencyKeyError):
        _materialize_uc(ctx).execute(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            session_id=ctx["session_id"],
            idempotency_key="",
        )
