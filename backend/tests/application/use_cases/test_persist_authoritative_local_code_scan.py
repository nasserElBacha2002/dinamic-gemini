"""Unit tests for PersistAuthoritativeLocalCodeScanResultUseCase (corrections)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.use_cases.aisles.persist_authoritative_local_code_scan import (
    AUTH_CLIENT_FILE_MISMATCH,
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


def _uc(*, enabled: bool = True, user_id: str = "user-1", client_file_id: str = "cf-1"):
    aisles = MemoryAisleRepository()
    aisles.save(_aisle())
    assets = MemorySourceAssetRepository()
    assets.save(_asset(client_file_id=client_file_id))
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


def test_create_ok_uses_server_confirmed_at():
    uc, repo = _uc()
    result = uc.execute(_cmd())
    assert result.status == "OK"
    assert result.applied_at is None
    saved = repo.get_by_id("result-1")
    assert saved is not None
    assert saved.confirmed_by == "user-1"
    assert saved.server_confirmed_at == datetime(2026, 7, 24, 12, 0, 1, tzinfo=timezone.utc)
    assert saved.client_confirmed_at == datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_duplicate_same_content():
    uc, _ = _uc()
    first = uc.execute(_cmd())
    second = uc.execute(_cmd())
    assert second.duplicate is True
    assert second.result_version == first.result_version


def test_same_result_id_different_content_conflicts():
    uc, _ = _uc()
    uc.execute(_cmd())
    result = uc.execute(_cmd(internal_code="OTHER"))
    assert result.status == "CONFLICT"
    assert result.error_code == AUTH_IDEMPOTENCY_CONFLICT


def test_new_version_supersedes_atomically():
    uc, repo = _uc()
    uc.execute(_cmd())
    result = uc.execute(
        _cmd(result_id="result-2", internal_code="XYZ999", source="LOCAL_MANUAL_CORRECTION")
    )
    assert result.status == "OK"
    assert result.result_version == 2
    assert result.supersedes_result_id == "result-1"
    assert repo.get_by_id("result-1").is_current is False
    assert repo.get_current_for_asset("asset-1").id == "result-2"


def test_client_file_mismatch():
    uc, _ = _uc(client_file_id="cf-other")
    result = uc.execute(_cmd(client_file_id="cf-1"))
    assert result.status == "REJECTED"
    assert result.error_code == AUTH_CLIENT_FILE_MISMATCH


def test_future_client_confirmed_at_rejected():
    uc, _ = _uc()
    result = uc.execute(
        _cmd(confirmed_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    )
    assert result.status == "REJECTED"
    assert result.error_code == AUTH_VALIDATION_FAILED
    assert "client_confirmed_at_future" in result.validation_errors


def test_server_source_not_allowed():
    uc, _ = _uc()
    result = uc.execute(_cmd(source="SERVER_CODE_SCAN"))
    assert result.status == "REJECTED"
