"""Sprint 2 capture session use cases (memory repositories)."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import (
    CaptureSessionInvalidStateError,
    CaptureSessionNotAcceptingUploadsError,
    CaptureSessionNotFoundError,
    TooManyFilesPerUploadError,
    InventoryNotFoundError,
    OpenCaptureSessionExistsError,
)
from src.application.ports.clock import Clock
from src.application.use_cases.cancel_capture_session import CancelCaptureSessionUseCase
from src.application.use_cases.close_capture_session import CloseCaptureSessionUseCase
from src.application.use_cases.create_capture_session import CreateCaptureSessionUseCase
from src.application.use_cases.get_capture_session_detail import GetCaptureSessionDetailUseCase
from src.application.use_cases.list_capture_sessions import ListCaptureSessionsUseCase
from src.application.use_cases.upload_capture_session_staging_items import (
    UploadCaptureSessionStagingItemsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.capture.entities import CaptureSessionStatus, CaptureTimeSource
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_capture_session_item_repository import (
    MemoryCaptureSessionItemRepository,
)
from src.infrastructure.repositories.memory_capture_session_repository import (
    MemoryCaptureSessionRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter


def _pillow_time_extractor():
    from src.application.services.capture_staging_time_metadata import (
        PillowCaptureStagingTimeMetadataExtractor,
    )

    return PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=0.85,
        confidence_mtime=0.55,
        confidence_fallback=0.35,
    )


class _FixedClock(Clock):
    def __init__(self, t: datetime) -> None:
        self._t = t

    def now(self) -> datetime:
        return self._t


def _seed_inv_aisle() -> tuple[MemoryInventoryRepository, MemoryAisleRepository, str, str]:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inv_id = str(uuid4())
    aisle_id = str(uuid4())
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
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


def test_create_session_success_and_list() -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    MemoryCaptureSessionItemRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    create_uc = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=1,
    )
    s = create_uc.execute(inv_id, aisle_id)
    assert s.status == CaptureSessionStatus.DRAFT
    assert s.inventory_id == inv_id
    assert s.aisle_id == aisle_id

    list_uc = ListCaptureSessionsUseCase(
        inventory_repo=inv_repo,
        session_repo=session_repo,
        default_page_size=25,
        max_page_size=200,
    )
    out = list_uc.execute(inv_id)
    assert out.total_items == 1
    assert out.items[0].id == s.id


def test_create_inventory_level_session_without_aisle() -> None:
    inv_repo, aisle_repo, inv_id, _aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    create_uc = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=1,
    )
    s = create_uc.execute(inv_id)
    assert s.inventory_id == inv_id
    assert s.aisle_id is None
    assert s.status == CaptureSessionStatus.DRAFT

    # Per-aisle open-session cap does not apply when session has no aisle yet.
    s2 = create_uc.execute(inv_id)
    assert s2.id != s.id
    assert s2.aisle_id is None


def test_inventory_level_session_upload_close_cancel_flow(tmp_path: Path) -> None:
    inv_repo, aisle_repo, inv_id, _aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    create_uc = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=1,
    )
    session = create_uc.execute(inv_id)
    assert session.aisle_id is None

    upload_uc = UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=V3ArtifactStorageAdapter(tmp_path),
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    )
    batch = upload_uc.execute(
        inventory_id=inv_id,
        aisle_id=None,
        session_id=session.id,
        files=[UploadedFile("inv-level.jpg", BytesIO(b"abc-inv"), "image/jpeg")],
    )
    assert len(batch.items) == 1
    assert batch.items[0].import_status.value == "imported"
    assert batch.errors == ()

    closed = CloseCaptureSessionUseCase(
        session_repo=session_repo, item_repo=item_repo, clock=clock
    ).execute(
        inventory_id=inv_id,
        session_id=session.id,
        aisle_id=None,
    )
    assert closed.status == CaptureSessionStatus.READY_FOR_REVIEW
    assert closed.closed_at is not None

    cancelled = CancelCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=V3ArtifactStorageAdapter(tmp_path / "cancel"),
        clock=clock,
    ).execute(
        inventory_id=inv_id,
        session_id=session.id,
        aisle_id=None,
    )
    assert cancelled.status == CaptureSessionStatus.CANCELLED


def test_create_fails_when_inventory_missing() -> None:
    inv_repo, aisle_repo, _inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    clock = _FixedClock(datetime.now(timezone.utc))
    create_uc = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=1,
    )
    with pytest.raises(InventoryNotFoundError):
        create_uc.execute("missing-inv", aisle_id)


def test_create_fails_when_aisle_wrong_inventory() -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    other_inv_id = str(uuid4())
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo.save(
        Inventory(
            id=other_inv_id,
            name="Other inv",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
    )
    session_repo = MemoryCaptureSessionRepository()
    clock = _FixedClock(datetime.now(timezone.utc))
    create_uc = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=1,
    )
    from src.application.errors import AisleNotFoundError

    with pytest.raises(AisleNotFoundError):
        create_uc.execute(other_inv_id, aisle_id)


def test_create_respects_open_session_cap() -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    create_uc = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=1,
    )
    create_uc.execute(inv_id, aisle_id)
    with pytest.raises(OpenCaptureSessionExistsError):
        create_uc.execute(inv_id, aisle_id)


def test_close_then_reopen_allowed(tmp_path: Path) -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    clock = _FixedClock(datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    create_uc = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=1,
    )
    s = create_uc.execute(inv_id, aisle_id)
    store = V3ArtifactStorageAdapter(tmp_path)
    UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=store,
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    ).execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=s.id,
        files=[UploadedFile("a.jpg", BytesIO(b"x"), "image/jpeg")],
    )
    close_uc = CloseCaptureSessionUseCase(
        session_repo=session_repo, item_repo=item_repo, clock=clock
    )
    closed = close_uc.execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id)
    assert closed.status == CaptureSessionStatus.READY_FOR_REVIEW
    assert closed.closed_at is not None
    s2 = create_uc.execute(inv_id, aisle_id)
    assert s2.id != s.id


def test_close_rejects_cancelled(tmp_path: Path) -> None:
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
        max_open_sessions_per_aisle=5,
    ).execute(inv_id, aisle_id)
    CancelCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=store,
        clock=clock,
    ).execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id)
    with pytest.raises(CaptureSessionInvalidStateError):
        CloseCaptureSessionUseCase(
            session_repo=session_repo, item_repo=item_repo, clock=clock
        ).execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id)


def test_close_draft_without_imported_items_rejected() -> None:
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
    close_uc = CloseCaptureSessionUseCase(
        session_repo=session_repo, item_repo=item_repo, clock=clock
    )
    with pytest.raises(CaptureSessionInvalidStateError):
        close_uc.execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id)


def test_staging_file_too_large(tmp_path: Path) -> None:
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
    upload_uc = UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=V3ArtifactStorageAdapter(tmp_path),
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=3,
        time_metadata_extractor=_pillow_time_extractor(),
    )
    batch = upload_uc.execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=s.id,
        files=[UploadedFile("a.jpg", BytesIO(b"abcd"), "image/jpeg")],
    )
    assert len(batch.items) == 0
    assert len(batch.errors) == 1
    assert batch.errors[0].code == "CAPTURE_SESSION_STAGING_FILE_TOO_LARGE"


def test_staging_upload_rejects_more_than_global_file_limit(tmp_path: Path) -> None:
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
    upload_uc = UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=V3ArtifactStorageAdapter(tmp_path),
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    )
    five_files = [
        UploadedFile(f"{i}.jpg", BytesIO(bytes([i + 1])), "image/jpeg") for i in range(5)
    ]
    batch = upload_uc.execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=s.id,
        files=five_files,
    )
    assert len(batch.items) == 5
    with pytest.raises(TooManyFilesPerUploadError):
        upload_uc.execute(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            session_id=s.id,
            files=[
                UploadedFile(f"{i}.jpg", BytesIO(bytes([i])), "image/jpeg")
                for i in range(6)
            ],
        )


def test_upload_creates_item_no_source_asset(tmp_path: Path) -> None:
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
    store = V3ArtifactStorageAdapter(tmp_path)
    upload_uc = UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=store,
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    )
    files = [
        UploadedFile(
            original_filename="a.jpg",
            file_obj=BytesIO(b"abc"),
            content_type="image/jpeg",
        )
    ]
    batch = upload_uc.execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id, files=files)
    assert len(batch.items) == 1
    assert batch.errors == ()
    assert batch.items[0].staging_storage_key.startswith("capture/staging/")
    assert batch.items[0].content_hash is not None
    assert batch.items[0].linked_source_asset_id is None
    assert batch.items[0].effective_capture_time is not None
    assert batch.items[0].time_source == CaptureTimeSource.FALLBACK_CLOCK
    refreshed = session_repo.get_by_id(s.id)
    assert refreshed is not None
    assert refreshed.status == CaptureSessionStatus.IMPORTING


def test_upload_rejected_after_cancel(tmp_path: Path) -> None:
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
    store = V3ArtifactStorageAdapter(tmp_path)
    CancelCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=store,
        clock=clock,
    ).execute(inventory_id=inv_id, aisle_id=aisle_id, session_id=s.id)
    upload_uc = UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=store,
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    )
    with pytest.raises(CaptureSessionNotAcceptingUploadsError):
        upload_uc.execute(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            session_id=s.id,
            files=[
                UploadedFile(
                    original_filename="a.jpg",
                    file_obj=BytesIO(b"x"),
                    content_type="image/jpeg",
                )
            ],
        )


def test_upload_duplicate_content_rejected(tmp_path: Path) -> None:
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
    store = V3ArtifactStorageAdapter(tmp_path)
    upload_uc = UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=store,
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    )
    body = b"same-bytes"
    first = upload_uc.execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=s.id,
        files=[
            UploadedFile("1.jpg", BytesIO(body), "image/jpeg"),
        ],
    )
    assert len(first.errors) == 0
    second = upload_uc.execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=s.id,
        files=[
            UploadedFile("2.jpg", BytesIO(body), "image/jpeg"),
        ],
    )
    assert len(second.items) == 0
    assert len(second.errors) == 1
    assert second.errors[0].code == "CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT"


def test_upload_mixed_batch_partial_success(tmp_path: Path) -> None:
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
    upload_uc = UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=V3ArtifactStorageAdapter(tmp_path),
        clock=clock,
        staging_prefix="capture/staging",
        max_upload_bytes=1024 * 1024,
        time_metadata_extractor=_pillow_time_extractor(),
    )
    body = b"unique-for-mixed"
    batch = upload_uc.execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        session_id=s.id,
        files=[
            UploadedFile("ok.jpg", BytesIO(body), "image/jpeg"),
            UploadedFile("empty.jpg", BytesIO(b""), "image/jpeg"),
            UploadedFile("dup.jpg", BytesIO(body), "image/jpeg"),
        ],
    )
    assert len(batch.items) == 1
    assert len(batch.errors) == 2
    assert batch.errors[0].file_index == 1
    assert batch.errors[0].code == "ZERO_BYTE_FILE"
    assert batch.errors[1].file_index == 2
    assert batch.errors[1].code == "CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT"


def test_get_detail_not_found_wrong_inventory() -> None:
    inv_repo, aisle_repo, inv_id, aisle_id = _seed_inv_aisle()
    other_inv_id = str(uuid4())
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo.save(
        Inventory(
            id=other_inv_id,
            name="Other inv",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
    )
    session_repo = MemoryCaptureSessionRepository()
    item_repo = MemoryCaptureSessionItemRepository()
    clock = _FixedClock(datetime.now(timezone.utc))
    s = CreateCaptureSessionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=3,
    ).execute(inv_id, aisle_id)
    detail_uc = GetCaptureSessionDetailUseCase(
        inventory_repo=inv_repo,
        session_repo=session_repo,
        item_repo=item_repo,
    )
    with pytest.raises(CaptureSessionNotFoundError):
        detail_uc.execute(other_inv_id, s.id)
