"""Sprint 3 capture session use cases: clock offset + assignment preview."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

import pytest

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import (
    CaptureSessionInvalidClockOffsetError,
    CaptureSessionInvalidStateError,
    CaptureSessionNotFoundError,
    CaptureSessionPreviewNotAllowedError,
)
from src.application.ports.clock import Clock
from src.application.services.capture_staging_time_metadata import (
    PillowCaptureStagingTimeMetadataExtractor,
)
from src.application.use_cases.close_capture_session import CloseCaptureSessionUseCase
from src.application.use_cases.compute_capture_session_assignment_preview import (
    ComputeCaptureSessionAssignmentPreviewUseCase,
)
from src.application.use_cases.create_capture_session import CreateCaptureSessionUseCase
from src.application.use_cases.update_capture_session_clock_offset import (
    UpdateCaptureSessionClockOffsetUseCase,
)
from src.application.use_cases.upload_capture_session_staging_items import (
    UploadCaptureSessionStagingItemsUseCase,
)
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
    CaptureTimeSource,
)
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_capture_session_item_repository import (
    MemoryCaptureSessionItemRepository,
)
from src.infrastructure.repositories.memory_capture_session_repository import (
    MemoryCaptureSessionRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter


class _FixedClock(Clock):
    def __init__(self, t: datetime) -> None:
        self._t = t

    def now(self) -> datetime:
        return self._t


def _pillow_time_extractor():
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
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
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


def test_preview_rejected_before_close(tmp_path) -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    pos_repo = MemoryPositionRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    s = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=3,
    ).execute(inv_id, aisle_id)
    UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=V3ArtifactStorageAdapter(tmp_path),
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    ).execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=s.id,
        files=[UploadedFile("a.jpg", BytesIO(b"abc"), "image/jpeg")],
    )
    preview_uc = ComputeCaptureSessionAssignmentPreviewUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        position_repo=pos_repo,
        clock=clock,
        preview_max_positions=100,
    )
    with pytest.raises(CaptureSessionPreviewNotAllowedError):
        preview_uc.execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id)


def test_preview_moves_session_and_offset_invalidates(tmp_path) -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    pos_repo = MemoryPositionRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    pos_repo.save(
        Position(
            id="pos-a",
            aisle_id=aisle_id,
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=t,
            updated_at=t,
            corrected_position_code="P1",
        )
    )
    s = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=3,
    ).execute(inv_id, aisle_id)
    UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=V3ArtifactStorageAdapter(tmp_path),
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    ).execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=s.id,
        files=[UploadedFile("a.jpg", BytesIO(b"unique-bytes-a"), "image/jpeg")],
    )
    CloseCaptureSessionUseCase(session_repo=session_repo, item_repo=item_repo, clock=clock).execute(
        inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id
    )
    off_uc = UpdateCaptureSessionClockOffsetUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        clock=clock,
        min_offset_seconds=-86400,
        max_offset_seconds=86400,
    )
    off_uc.execute(
        inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id, clock_offset_seconds=3600
    )
    sess = session_repo.get_by_id(s.id)
    assert sess is not None
    assert sess.clock_offset_seconds == 3600

    preview_uc = ComputeCaptureSessionAssignmentPreviewUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        position_repo=pos_repo,
        clock=clock,
        preview_max_positions=100,
    )
    preview_uc.execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id)
    sess2 = session_repo.get_by_id(s.id)
    assert sess2 is not None
    assert sess2.status == CaptureSessionStatus.ASSIGNMENT_PROPOSED
    items = list(item_repo.list_by_session(s.id))
    assert len(items) == 1
    assert items[0].assignment_status == CaptureSessionItemAssignmentStatus.PROPOSED

    off_uc.execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id, clock_offset_seconds=0)
    sess3 = session_repo.get_by_id(s.id)
    assert sess3 is not None
    assert sess3.status == CaptureSessionStatus.READY_FOR_REVIEW
    items3 = list(item_repo.list_by_session(s.id))
    assert items3[0].assignment_status == CaptureSessionItemAssignmentStatus.PENDING
    assert items3[0].adjusted_capture_time is None


def test_clock_offset_out_of_range() -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    s = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=3,
    ).execute(inv_id, aisle_id)
    off_uc = UpdateCaptureSessionClockOffsetUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        clock=clock,
        min_offset_seconds=-10,
        max_offset_seconds=10,
    )
    with pytest.raises(CaptureSessionInvalidClockOffsetError):
        off_uc.execute(
            inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id, clock_offset_seconds=99
        )


def test_clock_offset_blocked_after_cancel(tmp_path) -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    store = V3ArtifactStorageAdapter(tmp_path)
    s = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=3,
    ).execute(inv_id, aisle_id)
    from src.application.use_cases.cancel_capture_session import CancelCaptureSessionUseCase

    CancelCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=store,
        clock=clock,
    ).execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id)
    off_uc = UpdateCaptureSessionClockOffsetUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        clock=clock,
        min_offset_seconds=-86400,
        max_offset_seconds=86400,
    )
    with pytest.raises(CaptureSessionInvalidStateError):
        off_uc.execute(
            inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id, clock_offset_seconds=0
        )


def test_memory_repositories_roundtrip_sprint3_session_and_item_fields() -> None:
    """Memory repos store full domain objects; Sprint 3 columns must survive save/get/list."""
    now = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    session_repo.save(
        CaptureSession(
            id="s-s3",
            inventory_id="inv-s3",
            aisle_id="aisle-s3",
            status=CaptureSessionStatus.DRAFT,
            created_at=now,
            updated_at=now,
            clock_offset_seconds=-90,
        )
    )
    adj = datetime(2026, 4, 10, 11, 30, 0, tzinfo=timezone.utc)
    item_repo.save(
        CaptureSessionItem(
            id="it-s3",
            session_id="s-s3",
            staging_storage_key="blob",
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PROPOSED,
            updated_at=now,
            content_hash="h-s3",
            effective_capture_time=now,
            time_source=CaptureTimeSource.EXIF,
            time_confidence=0.88,
            adjusted_capture_time=adj,
            assignment_reason="preview: position_id=pos-9",
            preview_target_position_id="pos-9",
        )
    )
    got_s = session_repo.get_by_id_for_inventory("s-s3", "inv-s3")
    assert got_s is not None
    assert got_s.clock_offset_seconds == -90
    got_i = item_repo.get_by_id("it-s3")
    assert got_i is not None
    assert got_i.adjusted_capture_time == adj
    assert got_i.assignment_reason == "preview: position_id=pos-9"
    assert got_i.preview_target_position_id == "pos-9"
    listed = item_repo.list_by_session("s-s3")
    assert len(listed) == 1
    assert listed[0].preview_target_position_id == "pos-9"


def test_close_capture_session_use_case_dependencies_match_di_shape() -> None:
    """Constructor is ``session_repo``, ``item_repo``, ``clock`` only (same kwargs as FastAPI DI)."""
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    s = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=3,
    ).execute(inv_id, aisle_id)
    uc = CloseCaptureSessionUseCase(session_repo=session_repo, item_repo=item_repo, clock=clock)
    with pytest.raises(CaptureSessionInvalidStateError, match="no successfully imported items"):
        uc.execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id)
    with pytest.raises(CaptureSessionNotFoundError):
        uc.execute(inventory_id=inv_id, aisle_id=aisle_id, session_id="missing-session")
