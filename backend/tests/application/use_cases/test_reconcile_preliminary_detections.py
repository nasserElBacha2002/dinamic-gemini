"""Unit tests for Phase 5 reconciliation corrections."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.services.preliminary_detection_compare import (
    OUTCOME_MATCH_CODE_AND_QUANTITY,
    OUTCOME_NOT_COMPARABLE,
)
from src.application.services.resolve_comparable_remote_result import (
    REASON_GLOBAL_BATCH,
    REASON_JOB_FAILED,
    REASON_MULTIPLE_REMOTE,
    REASON_VERSION_UNKNOWN,
    ComparableRemoteResult,
    NotComparable,
    ResolveComparableRemoteResult,
)
from src.application.use_cases.aisles.reconcile_preliminary_detections import (
    EnqueuePreliminaryReconciliationsUseCase,
    EnqueueReconciliationCommand,
    ProcessPreliminaryReconciliationsUseCase,
    ReconciliationDisabledError,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.mobile_preliminary_detections.entities import MobilePreliminaryDetection
from src.infrastructure.persistence.memory_job_source_asset_repository import (
    MemoryJobSourceAssetRepository,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_mobile_preliminary_detection_repository import (
    MemoryMobilePreliminaryDetectionRepository,
)
from src.infrastructure.repositories.memory_preliminary_detection_reconciliation_repository import (
    MemoryPreliminaryDetectionReconciliationRepository,
)
from src.infrastructure.repositories.memory_processing_attempt_repository import (
    MemoryProcessingAttemptRepository,
)

NOW = datetime(2026, 7, 24, 15, 0, 0, tzinfo=timezone.utc)


class _Clock:
    def now(self) -> datetime:
        return NOW


def _aisle() -> Aisle:
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _job(*, status: JobStatus = JobStatus.SUCCEEDED) -> Job:
    return Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=status,
        payload_json={},
        created_at=NOW,
        updated_at=NOW,
        finished_at=NOW,
        prompt_version="pipeline@v1",
        configuration_snapshot_version=1,
    )


def _draft(**over) -> MobilePreliminaryDetection:
    base = dict(
        id="prelim-1",
        draft_id="draft-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        asset_id="asset-1",
        client_file_id="cf-1",
        status="RESOLVED",
        internal_code="ABC",
        quantity=5,
        quantity_status="PRESENT",
        detected_format="PIPE",
        detected_symbology="QR_CODE",
        candidate_count=1,
        parser_version="1.1.0",
        detector_version="mlkit-1",
        prepared_asset_sha256="a" * 64,
        payload_hash=None,
        processing_ms=10,
        detected_at=NOW,
        received_at=NOW,
        expires_at=NOW,
        validation_status="VALIDATED",
        validation_error_code=None,
        schema_version="1",
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(over)
    return MobilePreliminaryDetection(**base)


def _link(asset_id: str = "asset-1") -> JobSourceAssetLink:
    return JobSourceAssetLink(
        id="jsa-1",
        job_id="job-1",
        source_asset_id=asset_id,
        asset_role="primary",
        position_order=0,
        checksum=None,
        storage_key=None,
        mime_type=None,
        size_bytes=None,
        width=None,
        height=None,
        stage=None,
        provider_request_id=None,
        created_at=NOW,
    )


def test_resolve_global_batch_ignores_prior_code_scan() -> None:
    resolver = ResolveComparableRemoteResult()
    state = JobAssetProcessingState(
        id="s1",
        job_id="job-1",
        asset_id="asset-1",
        status=JobAssetProcessingStatus.RESOLVED,
        created_at=NOW,
        updated_at=NOW,
        last_strategy="GLOBAL_BATCH",
        finished_at=NOW,
    )
    prior = ProcessingAttempt(
        id="att-old",
        job_id="job-1",
        asset_id="asset-1",
        strategy="CODE_SCAN",
        attempt_number=1,
        status=ProcessingAttemptStatus.SUCCEEDED,
        created_at=NOW,
        finished_at=NOW,
        normalized_result={"internal_code": "ABC", "quantity": 5},
        logical_asset_attempt=True,
    )
    out = resolver.execute(
        local_status="RESOLVED",
        local_parser_version="1",
        local_detector_version="d",
        job_terminal=True,
        job_status=JobStatus.SUCCEEDED,
        asset_in_job_snapshot=True,
        state=state,
        attempts=[prior],
        remote_pipeline_version="p1",
    )
    assert isinstance(out, NotComparable)
    assert out.reason == REASON_GLOBAL_BATCH


def test_resolve_multiple_quantities() -> None:
    a1 = ProcessingAttempt(
        id="a1",
        job_id="job-1",
        asset_id="asset-1",
        strategy="CODE_SCAN",
        attempt_number=1,
        status=ProcessingAttemptStatus.SUCCEEDED,
        created_at=NOW,
        finished_at=NOW,
        normalized_result={"internal_code": "ABC", "quantity": 1},
        logical_asset_attempt=True,
    )
    a2 = ProcessingAttempt(
        id="a2",
        job_id="job-1",
        asset_id="asset-1",
        strategy="CODE_SCAN",
        attempt_number=2,
        status=ProcessingAttemptStatus.SUCCEEDED,
        created_at=NOW,
        finished_at=NOW,
        normalized_result={"internal_code": "ABC", "quantity": 9},
        logical_asset_attempt=True,
    )
    state = JobAssetProcessingState(
        id="s1",
        job_id="job-1",
        asset_id="asset-1",
        status=JobAssetProcessingStatus.RESOLVED,
        created_at=NOW,
        updated_at=NOW,
        last_strategy="CODE_SCAN",
        finished_at=NOW,
    )
    out = ResolveComparableRemoteResult().execute(
        local_status="RESOLVED",
        local_parser_version="1",
        local_detector_version="d",
        job_terminal=True,
        job_status=JobStatus.SUCCEEDED,
        asset_in_job_snapshot=True,
        state=state,
        attempts=[a1, a2],
        remote_pipeline_version="p1",
    )
    assert isinstance(out, NotComparable)
    assert out.reason == REASON_MULTIPLE_REMOTE


def test_resolve_failed_job_not_authority() -> None:
    out = ResolveComparableRemoteResult().execute(
        local_status="RESOLVED",
        local_parser_version="1",
        local_detector_version="d",
        job_terminal=True,
        job_status=JobStatus.FAILED,
        asset_in_job_snapshot=True,
        state=None,
        attempts=[],
        remote_pipeline_version="p1",
    )
    assert isinstance(out, NotComparable)
    assert out.reason == REASON_JOB_FAILED


def test_resolve_missing_remote_version() -> None:
    out = ResolveComparableRemoteResult().execute(
        local_status="RESOLVED",
        local_parser_version="1",
        local_detector_version="d",
        job_terminal=True,
        job_status=JobStatus.SUCCEEDED,
        asset_in_job_snapshot=True,
        state=None,
        attempts=[],
        remote_pipeline_version=None,
    )
    assert isinstance(out, NotComparable)
    assert out.reason == REASON_VERSION_UNKNOWN


def _world():
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(_aisle())
    job_repo = MemoryJobRepository()
    job_repo.save(_job())
    prelim = MemoryMobilePreliminaryDetectionRepository()
    prelim.insert(_draft())
    prelim.insert(
        _draft(
            id="prelim-out",
            draft_id="draft-out",
            asset_id="asset-out",
            client_file_id="cf-out",
        )
    )
    recon = MemoryPreliminaryDetectionReconciliationRepository()
    jsa = MemoryJobSourceAssetRepository()
    jsa.replace_for_job("job-1", [_link("asset-1")])
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    state_repo.save(
        JobAssetProcessingState(
            id="s1",
            job_id="job-1",
            asset_id="asset-1",
            status=JobAssetProcessingStatus.RESOLVED,
            created_at=NOW,
            updated_at=NOW,
            last_strategy="CODE_SCAN",
            finished_at=NOW,
        )
    )
    attempt_repo.save(
        ProcessingAttempt(
            id="att-1",
            job_id="job-1",
            asset_id="asset-1",
            strategy="CODE_SCAN",
            attempt_number=1,
            status=ProcessingAttemptStatus.SUCCEEDED,
            created_at=NOW,
            finished_at=NOW,
            normalized_result={"internal_code": "ABC", "quantity": 5},
            logical_asset_attempt=True,
        )
    )
    enqueue = EnqueuePreliminaryReconciliationsUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        preliminary_repo=prelim,
        reconciliation_repo=recon,
        job_source_asset_repo=jsa,
        enabled=True,
        clock=_Clock(),
    )
    process = ProcessPreliminaryReconciliationsUseCase(
        job_repo=job_repo,
        preliminary_repo=prelim,
        reconciliation_repo=recon,
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        job_source_asset_repo=jsa,
        enabled=True,
        clock=_Clock(),
    )
    return enqueue, process, recon


def test_enqueue_filters_snapshot_and_worker_completes() -> None:
    enqueue, process, recon = _world()
    enq = enqueue.execute(
        EnqueueReconciliationCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1")
    )
    assert enq.enqueued == 1
    assert len(enq.reconciliation_ids) == 1
    # asset-out not in snapshot — not enqueued
    batch = process.process_due_batch(limit=10)
    assert batch.claimed == 1
    assert batch.completed == 1
    row = recon.get_by_id(enq.reconciliation_ids[0])
    assert row is not None
    assert row.outcome == OUTCOME_MATCH_CODE_AND_QUANTITY
    assert row.job_id == "job-1"


def test_enqueue_idempotent_same_job() -> None:
    enqueue, process, recon = _world()
    cmd = EnqueueReconciliationCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1")
    first = enqueue.execute(cmd)
    process.process_due_batch(limit=10)
    second = enqueue.execute(cmd)
    assert second.enqueued == 0
    assert second.already_terminal == 1


def test_disabled() -> None:
    enqueue, _, _ = _world()
    enqueue._enabled = False
    with pytest.raises(ReconciliationDisabledError):
        enqueue.execute(
            EnqueueReconciliationCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1")
        )


def test_resolve_code_scan_ok() -> None:
    attempt = ProcessingAttempt(
        id="att-1",
        job_id="job-1",
        asset_id="asset-1",
        strategy="CODE_SCAN",
        attempt_number=1,
        status=ProcessingAttemptStatus.SUCCEEDED,
        created_at=NOW,
        finished_at=NOW,
        normalized_result={"internal_code": "ABC", "quantity": 5},
        logical_asset_attempt=True,
    )
    state = JobAssetProcessingState(
        id="s1",
        job_id="job-1",
        asset_id="asset-1",
        status=JobAssetProcessingStatus.RESOLVED,
        created_at=NOW,
        updated_at=NOW,
        last_strategy="CODE_SCAN",
        finished_at=NOW,
    )
    out = ResolveComparableRemoteResult().execute(
        local_status="RESOLVED",
        local_parser_version="1",
        local_detector_version="d",
        job_terminal=True,
        job_status=JobStatus.SUCCEEDED,
        asset_in_job_snapshot=True,
        state=state,
        attempts=[attempt],
        remote_pipeline_version="p1",
    )
    assert isinstance(out, ComparableRemoteResult)
    assert out.internal_code == "ABC"
