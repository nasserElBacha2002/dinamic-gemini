"""Unit tests for UpsertPreliminaryDetectionUseCase (Phase 4)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.use_cases.aisles.upsert_preliminary_detection import (
    PreliminaryDetectionIngestDisabledError,
    UpsertPreliminaryDetectionCommand,
    UpsertPreliminaryDetectionUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_mobile_preliminary_detection_repository import (
    MemoryMobilePreliminaryDetectionRepository,
)
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 24, 12, 0, 1, tzinfo=timezone.utc)


def _aisle() -> Aisle:
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.CREATED,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _asset(*, aisle_id: str = "aisle-1", client_file_id: str = "cf-1") -> SourceAsset:
    return SourceAsset(
        id="asset-1",
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="x.jpg",
        storage_path="/tmp/x.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        upload_client_file_id=client_file_id,
    )


def _cmd(**overrides) -> UpsertPreliminaryDetectionCommand:
    base = dict(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        draft_id="draft-1",
        schema_version="1",
        capture_session_id="sess-1",
        capture_photo_id="photo-1",
        client_file_id="cf-1",
        asset_id="asset-1",
        processing_mode="CODE_SCAN",
        status="RESOLVED",
        internal_code="ABC123",
        quantity=10,
        quantity_status="PRESENT",
        detected_format="PIPE",
        detected_symbology="QR_CODE",
        candidate_count=1,
        parser_version="1.1.0",
        detector_version="mlkit-barcode-1.0.0",
        prepared_asset_sha256="sha256:" + ("a" * 64),
        payload_hash="sha256:" + ("b" * 64),
        processing_ms=120,
        detected_at=datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return UpsertPreliminaryDetectionCommand(**base)


def _uc(
    *,
    enabled: bool = True,
    aisle: Aisle | None = None,
    asset: SourceAsset | None = None,
) -> UpsertPreliminaryDetectionUseCase:
    aisle_repo = MemoryAisleRepository()
    asset_repo = MemorySourceAssetRepository()
    prelim = MemoryMobilePreliminaryDetectionRepository()
    if aisle is not None:
        aisle_repo.save(aisle)
    else:
        aisle_repo.save(_aisle())
    if asset is not None:
        asset_repo.save(asset)
    else:
        asset_repo.save(_asset())
    return UpsertPreliminaryDetectionUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        preliminary_repo=prelim,
        clock=_FixedClock(),
        enabled=enabled,
    )


def test_disabled_raises():
    uc = _uc(enabled=False)
    with pytest.raises(PreliminaryDetectionIngestDisabledError):
        uc.execute(_cmd())


def test_create_validated():
    uc = _uc()
    result = uc.execute(_cmd())
    assert result.status == "VALIDATED"
    assert result.server_preliminary_id
    assert result.duplicate is False


def test_idempotent_repeat():
    uc = _uc()
    first = uc.execute(_cmd())
    second = uc.execute(_cmd())
    assert second.duplicate is True
    assert second.server_preliminary_id == first.server_preliminary_id
    assert second.status == "VALIDATED"


def test_idempotency_content_conflict():
    uc = _uc()
    uc.execute(_cmd())
    result = uc.execute(_cmd(internal_code="OTHER"))
    assert result.status == "CONFLICT"
    assert "IDEMPOTENCY_CONTENT_CONFLICT" in result.validation_errors


def test_asset_missing_pending():
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(_aisle())
    uc = UpsertPreliminaryDetectionUseCase(
        aisle_repo=aisle_repo,
        asset_repo=MemorySourceAssetRepository(),
        preliminary_repo=MemoryMobilePreliminaryDetectionRepository(),
        clock=_FixedClock(),
        enabled=True,
    )
    result = uc.execute(_cmd())
    assert result.status == "PENDING_ASSET"


def test_wrong_aisle_asset():
    uc = _uc(asset=_asset(aisle_id="other-aisle"))
    result = uc.execute(_cmd())
    assert result.status == "PENDING_ASSET"


def test_client_file_mismatch():
    uc = _uc(asset=_asset(client_file_id="other-cf"))
    result = uc.execute(_cmd())
    assert result.status == "REJECTED"
    assert "CLIENT_FILE_ID_MISMATCH" in result.validation_errors


def test_resolved_requires_code():
    uc = _uc()
    result = uc.execute(_cmd(internal_code=None))
    assert result.status == "REJECTED"
    assert "INTERNAL_CODE_REQUIRED_FOR_RESOLVED" in result.validation_errors


def test_invalid_hash():
    uc = _uc()
    result = uc.execute(_cmd(prepared_asset_sha256="not-a-hash"))
    assert result.status == "REJECTED"
    assert "PREPARED_ASSET_SHA256_INVALID" in result.validation_errors


def test_ambiguous_must_not_have_quantity():
    uc = _uc()
    result = uc.execute(_cmd(status="AMBIGUOUS", internal_code=None, quantity=5, quantity_status=None))
    assert result.status == "REJECTED"
    assert "AMBIGUOUS_MUST_NOT_HAVE_QUANTITY" in result.validation_errors


def test_same_image_versions_hash_dedupes_different_draft_id():
    uc = _uc()
    first = uc.execute(_cmd(draft_id="draft-a"))
    second = uc.execute(_cmd(draft_id="draft-b"))
    assert second.duplicate is True
    assert second.server_preliminary_id == first.server_preliminary_id
    assert second.draft_id == "draft-a"
