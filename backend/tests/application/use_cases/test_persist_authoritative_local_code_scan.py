"""Unit tests for PersistAuthoritativeLocalCodeScanResultUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.use_cases.aisles.persist_authoritative_local_code_scan import (
    AUTH_IDEMPOTENCY_CONFLICT,
    AUTH_VALIDATION_FAILED,
    AuthoritativeIngestDisabledError,
    PersistAuthoritativeLocalCodeScanCommand,
    PersistAuthoritativeLocalCodeScanResultUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_authoritative_local_code_scan_repository import (
    MemoryAuthoritativeLocalCodeScanRepository,
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


def _asset(*, aisle_id: str = "aisle-1") -> SourceAsset:
    return SourceAsset(
        id="asset-1",
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="x.jpg",
        storage_path="/tmp/x.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        upload_client_file_id="cf-1",
    )


def _cmd(**overrides) -> PersistAuthoritativeLocalCodeScanCommand:
    base = dict(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        asset_id="asset-1",
        result_id="result-1",
        schema_version="1",
        client_file_id="cf-1",
        internal_code="ABC123",
        quantity=10,
        quantity_status="PRESENT",
        source="LOCAL_CODE_SCAN",
        detected_internal_code="ABC123",
        detected_quantity=10,
        detected_symbology="QR_CODE",
        parser_version="1.0.0",
        detector_version="mlkit-1.0.0",
        prepared_asset_sha256="sha256:" + ("a" * 64),
        confirmed_at=datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return PersistAuthoritativeLocalCodeScanCommand(**base)


def _uc(*, enabled: bool = True, user_id: str = "user-1"):
    aisles = MemoryAisleRepository()
    aisles.save(_aisle())
    assets = MemorySourceAssetRepository()
    assets.save(_asset())
    repo = MemoryAuthoritativeLocalCodeScanRepository()
    return (
        PersistAuthoritativeLocalCodeScanResultUseCase(
            aisle_repo=aisles,
            asset_repo=assets,
            authoritative_repo=repo,
            clock=_FixedClock(),
            enabled=enabled,
            authenticated_user_id=user_id,
        ),
        repo,
    )


def test_disabled_raises():
    uc, _ = _uc(enabled=False)
    with pytest.raises(AuthoritativeIngestDisabledError):
        uc.execute(_cmd())


def test_create_ok():
    uc, repo = _uc()
    result = uc.execute(_cmd())
    assert result.status == "OK"
    assert result.result_version == 1
    assert result.is_current is True
    assert result.duplicate is False
    saved = repo.get_by_id("result-1")
    assert saved is not None
    assert saved.confirmed_by == "user-1"
    assert saved.internal_code == "ABC123"
    assert saved.detected_internal_code == "ABC123"


def test_duplicate_same_content():
    uc, _ = _uc()
    first = uc.execute(_cmd())
    second = uc.execute(_cmd())
    assert first.status == "OK"
    assert second.status == "OK"
    assert second.duplicate is True
    assert second.result_version == first.result_version


def test_same_result_id_different_content_conflicts():
    uc, _ = _uc()
    uc.execute(_cmd())
    result = uc.execute(_cmd(internal_code="OTHER"))
    assert result.status == "CONFLICT"
    assert result.error_code == AUTH_IDEMPOTENCY_CONFLICT


def test_new_version_supersedes():
    uc, repo = _uc()
    uc.execute(_cmd())
    result = uc.execute(_cmd(result_id="result-2", internal_code="XYZ999", source="LOCAL_MANUAL_CORRECTION"))
    assert result.status == "OK"
    assert result.result_version == 2
    assert result.supersedes_result_id == "result-1"
    old = repo.get_by_id("result-1")
    assert old is not None
    assert old.is_current is False
    current = repo.get_current_for_asset("asset-1")
    assert current is not None
    assert current.id == "result-2"


def test_invalid_code_rejected():
    uc, _ = _uc()
    result = uc.execute(_cmd(internal_code=""))
    assert result.status == "REJECTED"
    assert result.error_code == AUTH_VALIDATION_FAILED


def test_invalid_quantity_rejected():
    uc, _ = _uc()
    result = uc.execute(_cmd(quantity=0))
    assert result.status == "REJECTED"


def test_missing_quantity_ok():
    uc, repo = _uc()
    result = uc.execute(_cmd(quantity=None, quantity_status="MISSING"))
    assert result.status == "OK"
    saved = repo.get_by_id("result-1")
    assert saved is not None
    assert saved.quantity is None
    assert saved.quantity_status == "MISSING"


def test_asset_other_aisle_rejected():
    aisles = MemoryAisleRepository()
    aisles.save(_aisle())
    aisles.save(
        Aisle(
            id="aisle-2",
            inventory_id="inv-1",
            code="A2",
            status=AisleStatus.CREATED,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    assets = MemorySourceAssetRepository()
    assets.save(_asset(aisle_id="aisle-1"))
    repo = MemoryAuthoritativeLocalCodeScanRepository()
    uc = PersistAuthoritativeLocalCodeScanResultUseCase(
        aisle_repo=aisles,
        asset_repo=assets,
        authoritative_repo=repo,
        clock=_FixedClock(),
        enabled=True,
        authenticated_user_id="user-1",
    )
    result = uc.execute(_cmd(aisle_id="aisle-2", asset_id="asset-1"))
    assert result.status == "REJECTED"
    assert "asset_not_in_aisle" in result.validation_errors


def test_server_source_not_allowed_from_client():
    uc, _ = _uc()
    result = uc.execute(_cmd(source="SERVER_CODE_SCAN"))
    assert result.status == "REJECTED"
