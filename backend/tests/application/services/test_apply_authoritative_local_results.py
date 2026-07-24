"""Unit tests for ApplyAuthoritativeLocalResultsService (fail-closed corrections)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.application.errors import (
    AuthoritativeResultApplyFailedError,
    AuthoritativeResultStateConflictError,
)
from src.application.services.image_processing.apply_authoritative_local_results import (
    LOCAL_AUTHORITY_STRATEGY,
    RESOLVED_BY_LOCAL_AUTHORITY,
    ApplyAuthoritativeLocalResultsService,
)
from src.application.services.image_processing.processing_result_persister import (
    PersistOutcome,
    PersistSkipReason,
)
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_authoritative_local_code_scan_repository import (
    MemoryAuthoritativeLocalCodeScanRepository,
)
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 7, 24, 13, 0, 0, tzinfo=timezone.utc)


def _row(**overrides) -> AuthoritativeLocalCodeScanResult:
    now = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)
    base = dict(
        id="res-1",
        asset_id="asset-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        client_file_id="cf-1",
        result_version=1,
        supersedes_result_id=None,
        is_current=True,
        internal_code="ABC",
        quantity=1,
        quantity_status="PRESENT",
        source="LOCAL_CODE_SCAN",
        detected_internal_code="ABC",
        detected_quantity=1,
        detected_symbology="QR_CODE",
        parser_version="1",
        detector_version="mlkit",
        prepared_asset_sha256="sha256:" + ("b" * 64),
        content_hash="sha256:" + ("c" * 64),
        confirmed_by="user-1",
        client_confirmed_at=now,
        server_confirmed_at=now,
        server_received_at=now,
        confirmed_at=now,
        applied_job_id=None,
        applied_at=None,
        row_version=1,
        schema_version="1",
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return AuthoritativeLocalCodeScanResult(**base)


def _job() -> Job:
    return Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={},
        created_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )


def _asset() -> SourceAsset:
    return SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="x.jpg",
        storage_path="/tmp/x.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        upload_client_file_id="cf-1",
    )


def test_missing_row_fail_closed_when_required():
    repo = MemoryAuthoritativeLocalCodeScanRepository()
    state_repo = MemoryJobAssetProcessingStateRepository()
    persister = MagicMock()
    svc = ApplyAuthoritativeLocalResultsService(
        authoritative_repo=repo,
        result_persister=persister,
        state_repo=state_repo,
        clock=_Clock(),
        enabled=True,
        require_all_assets=True,
    )
    with pytest.raises(AuthoritativeResultApplyFailedError):
        svc.apply_for_job(
            job=_job(), aisle_id="aisle-1", inventory_id="inv-1", assets=[_asset()]
        )
    persister.persist.assert_not_called()


def test_does_not_mark_applied_when_resolved_by_remote():
    repo = MemoryAuthoritativeLocalCodeScanRepository()
    row = _row()
    repo.create_authoritative_version(
        new_result=row, expected_current_id=None, expected_row_version=None
    )
    state_repo = MemoryJobAssetProcessingStateRepository()
    now = _Clock().now()
    state_repo.save(
        JobAssetProcessingState(
            id="s1",
            job_id="job-1",
            asset_id="asset-1",
            status=JobAssetProcessingStatus.RESOLVED,
            created_at=now,
            updated_at=now,
            last_strategy="CODE_SCAN",
            version=1,
        )
    )
    svc = ApplyAuthoritativeLocalResultsService(
        authoritative_repo=repo,
        result_persister=MagicMock(),
        state_repo=state_repo,
        clock=_Clock(),
        enabled=True,
    )
    with pytest.raises(AuthoritativeResultStateConflictError):
        svc.apply_for_job(
            job=_job(), aisle_id="aisle-1", inventory_id="inv-1", assets=[_asset()]
        )
    fresh = repo.get_by_id("res-1")
    assert fresh is not None
    assert fresh.applied_at is None


def test_apply_success_marks_local_authority():
    repo = MemoryAuthoritativeLocalCodeScanRepository()
    row = _row()
    repo.create_authoritative_version(
        new_result=row, expected_current_id=None, expected_row_version=None
    )
    state_repo = MemoryJobAssetProcessingStateRepository()
    now = _Clock().now()
    state_repo.save(
        JobAssetProcessingState(
            id="s1",
            job_id="job-1",
            asset_id="asset-1",
            status=JobAssetProcessingStatus.PENDING,
            created_at=now,
            updated_at=now,
            version=1,
        )
    )
    persister = MagicMock()
    persister.persist.return_value = PersistOutcome(
        persisted=True, reconciled=False, active_result_id="ar-1"
    )
    svc = ApplyAuthoritativeLocalResultsService(
        authoritative_repo=repo,
        result_persister=persister,
        state_repo=state_repo,
        clock=_Clock(),
        enabled=True,
    )
    out = svc.apply_for_job(
        job=_job(), aisle_id="aisle-1", inventory_id="inv-1", assets=[_asset()]
    )
    assert out.applied == 1
    state = state_repo.get_by_job_and_asset("job-1", "asset-1")
    assert state is not None
    assert state.last_strategy == LOCAL_AUTHORITY_STRATEGY
    assert state.error_code == RESOLVED_BY_LOCAL_AUTHORITY
    fresh = repo.get_by_id(repo.get_current_for_asset("asset-1").id)
    assert fresh.applied_job_id == "job-1"
    assert fresh.applied_at is not None


def test_persist_skip_fail_closed():
    repo = MemoryAuthoritativeLocalCodeScanRepository()
    repo.create_authoritative_version(
        new_result=_row(), expected_current_id=None, expected_row_version=None
    )
    state_repo = MemoryJobAssetProcessingStateRepository()
    now = _Clock().now()
    state_repo.save(
        JobAssetProcessingState(
            id="s1",
            job_id="job-1",
            asset_id="asset-1",
            status=JobAssetProcessingStatus.PENDING,
            created_at=now,
            updated_at=now,
            version=1,
        )
    )
    persister = MagicMock()
    persister.persist.return_value = PersistOutcome(
        persisted=False,
        reconciled=False,
        skipped_reason=PersistSkipReason.MISSING_CODE_OR_QUANTITY,
    )
    svc = ApplyAuthoritativeLocalResultsService(
        authoritative_repo=repo,
        result_persister=persister,
        state_repo=state_repo,
        clock=_Clock(),
        enabled=True,
    )
    with pytest.raises(AuthoritativeResultApplyFailedError):
        svc.apply_for_job(
            job=_job(), aisle_id="aisle-1", inventory_id="inv-1", assets=[_asset()]
        )
