"""Unit tests for Phase 2 corrections: strategy resolver, image/aisle orchestrators, lease,
coverage resolver, and the ``for_aisles`` batch config query."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.application.services.aisle_identification_configuration_query import (
    AisleIdentificationConfigurationQuery,
)
from src.application.services.image_processing.aisle_processing_orchestrator import (
    AisleProcessingOrchestrator,
)
from src.application.services.image_processing.asset_result_coverage_resolver import (
    AssetResultCoverageResolver,
    AssetResultCoverageStatus,
)
from src.application.services.image_processing.image_processing_orchestrator import (
    ImageProcessingOrchestrator,
)
from src.application.services.image_processing.legacy_llm_processing_strategy import (
    LegacyBatchOutcome,
    LegacyLlmProcessingStrategy,
)
from src.application.services.image_processing.processing_strategy_resolver import (
    STRATEGY_LEGACY_LLM,
    ProcessingStrategyResolver,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import (
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.evidence.entities import Evidence, EvidenceType
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_attempt import ProcessingAttemptStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.traceability import TraceabilityStatus
from src.infrastructure.repositories.memory_batch_processing_attempt_repository import (
    MemoryBatchProcessingAttemptRepository,
)
from src.infrastructure.repositories.memory_evidence_repository import (
    MemoryEvidenceRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import (
    MemoryInventoryRepository,
)
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)
from src.infrastructure.repositories.memory_job_processing_lease_repository import (
    MemoryJobProcessingLeaseRepository,
)
from src.infrastructure.repositories.memory_position_repository import (
    MemoryPositionRepository,
)
from src.infrastructure.repositories.memory_processing_attempt_repository import (
    MemoryProcessingAttemptRepository,
)
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _job(**kwargs: object) -> Job:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base: dict[str, object] = dict(
        id="job1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="a1",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "a1"},
        created_at=now,
        updated_at=now,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        identification_mode_source=AisleIdentificationModeSource.REQUEST,
        configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
        execution_strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM_TEMPORARY,
        provider_name="gemini",
        model_name="m",
        prompt_key="global_v22",
    )
    base.update(kwargs)
    return Job(**base)  # type: ignore[arg-type]


def _aisle(now: datetime, aisle_id: str = "a1", inventory_id: str = "inv1") -> Aisle:
    return Aisle(
        id=aisle_id,
        inventory_id=inventory_id,
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


def _asset(asset_id: str, now: datetime, aisle_id: str = "a1") -> SourceAsset:
    return SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename=f"{asset_id}.jpg",
        storage_path=f"/{asset_id}.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )


def _build_orchestrator(
    clock: FixedClock,
    *,
    attempts_enabled: bool = True,
    abandoned_processing_ttl_seconds: int = 900,
    lease_duration_seconds: int = 900,
) -> tuple[AisleProcessingOrchestrator, dict[str, object]]:
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    lease_repo = MemoryJobProcessingLeaseRepository()
    batch_attempt_repo = MemoryBatchProcessingAttemptRepository()
    result_evidence_repo = MemoryResultEvidenceRepository()
    evidence_repo = MemoryEvidenceRepository()
    position_repo = MemoryPositionRepository()

    image_orch = ImageProcessingOrchestrator(
        state_repo, attempt_repo, clock, attempts_enabled=attempts_enabled
    )
    coverage_resolver = AssetResultCoverageResolver(
        result_evidence_repo=result_evidence_repo,
        evidence_repo=evidence_repo,
        position_repo=position_repo,
    )
    orch = AisleProcessingOrchestrator(
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        lease_repo=lease_repo,
        batch_attempt_repo=batch_attempt_repo,
        clock=clock,
        image_orchestrator=image_orch,
        strategy_resolver=ProcessingStrategyResolver(),
        legacy_strategy=LegacyLlmProcessingStrategy(),
        coverage_resolver=coverage_resolver,
        attempts_enabled=attempts_enabled,
        abandoned_processing_ttl_seconds=abandoned_processing_ttl_seconds,
        lease_duration_seconds=lease_duration_seconds,
    )
    repos = {
        "state_repo": state_repo,
        "attempt_repo": attempt_repo,
        "lease_repo": lease_repo,
        "batch_attempt_repo": batch_attempt_repo,
        "result_evidence_repo": result_evidence_repo,
        "evidence_repo": evidence_repo,
        "position_repo": position_repo,
    }
    return orch, repos


def _result_evidence_row(
    *, job_id: str, aisle_id: str, asset_id: str, has_valid_evidence: bool, now: datetime
) -> ResultEvidenceRecord:
    return ResultEvidenceRecord(
        id=f"re-{job_id}-{asset_id}",
        job_id=job_id,
        inventory_id="inv1",
        aisle_id=aisle_id,
        position_id="p1",
        entity_uid="p1",
        model_entity_id=None,
        raw_manifest_entry_id=None,
        manifest_entry_id=None,
        raw_source_image_id=asset_id,
        resolved_manifest_entry_id=None,
        source_image_id=asset_id,
        source_asset_id=asset_id,
        traceability_status=(
            TraceabilityStatus.VALID.value if has_valid_evidence else TraceabilityStatus.MISSING.value
        ),
        traceability_warning=None,
        role=ResultEvidenceRole.PRIMARY_EVIDENCE,
        provider="test",
        model_name=None,
        schema_version=None,
        manifest_version=None,
        has_valid_evidence=has_valid_evidence,
        evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Strategy resolver
# ---------------------------------------------------------------------------


def test_strategy_resolver_always_legacy_for_phase2_modes() -> None:
    resolver = ProcessingStrategyResolver()
    for mode in (
        AisleIdentificationMode.LEGACY_LLM,
        AisleIdentificationMode.CODE_SCAN,
        AisleIdentificationMode.INTERNAL_OCR,
    ):
        job = _job(identification_mode=mode)
        assert (
            resolver.resolve_strategy_key(job, pipeline_enabled=True, orchestrator_enabled=True)
            == STRATEGY_LEGACY_LLM
        )
        assert (
            resolver.resolve_strategy_key(job, pipeline_enabled=False, orchestrator_enabled=False)
            == STRATEGY_LEGACY_LLM
        )


# ---------------------------------------------------------------------------
# Image-level acquire / terminal policy
# ---------------------------------------------------------------------------


def test_image_orchestrator_skips_already_resolved() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    image_orch = ImageProcessingOrchestrator(state_repo, attempt_repo, clock, attempts_enabled=True)

    state = JobAssetProcessingState(
        id="s1",
        job_id="job1",
        asset_id="asset-1",
        status=JobAssetProcessingStatus.RESOLVED,
        created_at=now,
        updated_at=now,
    )
    state_repo.save(state)
    acquired = image_orch.acquire_for_processing(job_id="job1", asset_id="asset-1", strategy="LEGACY_LLM")
    assert acquired is None


def test_try_acquire_race_only_one_wins() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    image_orch = ImageProcessingOrchestrator(state_repo, attempt_repo, clock, attempts_enabled=False)

    state = JobAssetProcessingState(
        id="s1",
        job_id="job1",
        asset_id="asset-1",
        status=JobAssetProcessingStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    state_repo.save(state)

    first = image_orch.acquire_for_processing(
        job_id="job1", asset_id="asset-1", strategy="LEGACY_LLM", worker_token="w1"
    )
    second = image_orch.acquire_for_processing(
        job_id="job1", asset_id="asset-1", strategy="LEGACY_LLM", worker_token="w2"
    )
    assert first is not None
    assert second is None


def test_failed_technical_not_reacquired() -> None:
    """FAILED_TECHNICAL is terminal within the same job — never eligible for re-acquire."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    image_orch = ImageProcessingOrchestrator(state_repo, attempt_repo, clock, attempts_enabled=False)

    state = JobAssetProcessingState(
        id="s1",
        job_id="job1",
        asset_id="asset-1",
        status=JobAssetProcessingStatus.FAILED_TECHNICAL,
        created_at=now,
        updated_at=now,
    )
    state_repo.save(state)

    acquired = image_orch.acquire_for_processing(job_id="job1", asset_id="asset-1", strategy="LEGACY_LLM")
    assert acquired is None
    assert image_orch.is_terminal(state_repo.get_by_job_and_asset("job1", "asset-1"))


# ---------------------------------------------------------------------------
# Lease
# ---------------------------------------------------------------------------


def test_lease_acquire_second_loses() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lease_repo = MemoryJobProcessingLeaseRepository()

    first = lease_repo.try_acquire_lease(
        job_id="job1",
        strategy="LEGACY_LLM",
        execution_scope="AISLE_BATCH",
        worker_token="w1",
        now=now,
        lease_duration_seconds=900,
    )
    second = lease_repo.try_acquire_lease(
        job_id="job1",
        strategy="LEGACY_LLM",
        execution_scope="AISLE_BATCH",
        worker_token="w2",
        now=now,
        lease_duration_seconds=900,
    )
    assert first is not None
    assert second is None

    # Once released, a different worker can acquire it.
    lease_repo.release(first.id, worker_token="w1", now=now)
    third = lease_repo.try_acquire_lease(
        job_id="job1",
        strategy="LEGACY_LLM",
        execution_scope="AISLE_BATCH",
        worker_token="w2",
        now=now,
        lease_duration_seconds=900,
    )
    assert third is not None
    assert third.worker_token == "w2"


def test_process_with_legacy_batch_skips_runner_when_lease_busy() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    orch, repos = _build_orchestrator(clock)
    job = _job()
    aisle = _aisle(now)
    asset = _asset("asset-1", now)

    repos["lease_repo"].try_acquire_lease(  # type: ignore[union-attr]
        job_id=job.id,
        strategy="LEGACY_LLM",
        execution_scope="AISLE_BATCH",
        worker_token="other-worker",
        now=now,
        lease_duration_seconds=900,
    )

    runner_calls: list[bool] = []

    def runner() -> LegacyBatchOutcome:
        runner_calls.append(True)
        return LegacyBatchOutcome(ok=True)

    out = orch.process_with_legacy_batch(
        job=job,
        aisle=aisle,
        assets=[asset],
        batch_runner=runner,
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )
    assert runner_calls == []
    assert out.legacy.ok is False
    assert out.legacy.skipped_busy is True
    assert out.legacy.error_message == "BATCH_LEASE_NOT_ACQUIRED"


# ---------------------------------------------------------------------------
# AisleProcessingOrchestrator.process_with_legacy_batch
# ---------------------------------------------------------------------------


def test_aisle_orchestrator_synthesizes_resolved_and_unrecognized() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    orch, repos = _build_orchestrator(clock, attempts_enabled=True)
    job = _job()
    aisle = _aisle(now)
    assets = [_asset("asset-1", now), _asset("asset-2", now)]

    repos["result_evidence_repo"].save_many(  # type: ignore[union-attr]
        [
            _result_evidence_row(
                job_id=job.id, aisle_id=aisle.id, asset_id="asset-1", has_valid_evidence=True, now=now
            )
        ]
    )

    def runner() -> LegacyBatchOutcome:
        return LegacyBatchOutcome(ok=True)

    out = orch.process_with_legacy_batch(
        job=job,
        aisle=aisle,
        assets=assets,
        batch_runner=runner,
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )
    assert out.progress.total == 2
    assert out.progress.resolved == 1
    assert out.progress.unrecognized == 1

    state_repo = repos["state_repo"]
    s1 = state_repo.get_by_job_and_asset("job1", "asset-1")  # type: ignore[union-attr]
    s2 = state_repo.get_by_job_and_asset("job1", "asset-2")  # type: ignore[union-attr]
    assert s1 is not None and s1.status == JobAssetProcessingStatus.RESOLVED
    assert s2 is not None and s2.status == JobAssetProcessingStatus.UNRECOGNIZED

    attempts = repos["attempt_repo"].list_by_job("job1")  # type: ignore[union-attr]
    assert len(attempts) == 2
    assert all(a.status != ProcessingAttemptStatus.STARTED for a in attempts)

    lease = repos["lease_repo"].get_by_job_strategy_scope(  # type: ignore[union-attr]
        job.id, "LEGACY_LLM", "AISLE_BATCH"
    )
    assert lease is not None and lease.status.value == "COMPLETED"

    batch_attempts = repos["batch_attempt_repo"].get_started_by_job(  # type: ignore[union-attr]
        job.id, "LEGACY_LLM", "AISLE_BATCH"
    )
    assert batch_attempts == []  # finalized, no longer STARTED


def test_attempts_created_before_runner_called() -> None:
    """Logical attempts must exist (STARTED) before the physical batch_runner executes."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    orch, repos = _build_orchestrator(clock, attempts_enabled=True)
    job = _job()
    aisle = _aisle(now)
    asset = _asset("asset-1", now)

    seen_started_counts: list[int] = []

    def runner() -> LegacyBatchOutcome:
        attempts = repos["attempt_repo"].list_by_job(job.id)  # type: ignore[union-attr]
        seen_started_counts.append(
            sum(1 for a in attempts if a.status == ProcessingAttemptStatus.STARTED)
        )
        return LegacyBatchOutcome(ok=True)

    orch.process_with_legacy_batch(
        job=job,
        aisle=aisle,
        assets=[asset],
        batch_runner=runner,
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )
    assert seen_started_counts == [1]


def test_attempt_count_increments_even_when_attempts_disabled() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    orch, repos = _build_orchestrator(clock, attempts_enabled=False)
    job = _job()
    aisle = _aisle(now)
    asset = _asset("asset-1", now)

    orch.process_with_legacy_batch(
        job=job,
        aisle=aisle,
        assets=[asset],
        batch_runner=lambda: LegacyBatchOutcome(ok=True),
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )
    state = repos["state_repo"].get_by_job_and_asset(job.id, asset.id)  # type: ignore[union-attr]
    assert state is not None
    assert state.attempt_count == 1
    assert repos["attempt_repo"].list_by_job(job.id) == []  # type: ignore[union-attr]


def test_process_with_legacy_batch_failure_marks_failed_technical_and_fails_lease() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    orch, repos = _build_orchestrator(clock, attempts_enabled=True)
    job = _job()
    aisle = _aisle(now)
    asset = _asset("asset-1", now)

    out = orch.process_with_legacy_batch(
        job=job,
        aisle=aisle,
        assets=[asset],
        batch_runner=lambda: LegacyBatchOutcome(ok=False, error_message="boom"),
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )
    assert out.legacy.ok is False
    state = repos["state_repo"].get_by_job_and_asset(job.id, asset.id)  # type: ignore[union-attr]
    assert state is not None and state.status == JobAssetProcessingStatus.FAILED_TECHNICAL
    lease = repos["lease_repo"].get_by_job_strategy_scope(  # type: ignore[union-attr]
        job.id, "LEGACY_LLM", "AISLE_BATCH"
    )
    assert lease is not None and lease.status.value == "FAILED"


def test_process_with_legacy_batch_runner_exception_closes_bookkeeping_then_reraises() -> None:
    """batch_runner raising must still propagate out of process_with_legacy_batch — the
    executor's top-level unexpected-failure handler owns marking job/aisle FAILED (it
    re-fetches the job before writing, so it is safe even if the runner's own failure
    reporting already partially failed) — but our own lease/attempt/state bookkeeping must
    be closed out first so a concurrent worker is not blocked forever."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    orch, repos = _build_orchestrator(clock, attempts_enabled=True)
    job = _job()
    aisle = _aisle(now)
    asset = _asset("asset-1", now)

    def failing_runner() -> LegacyBatchOutcome:
        raise RuntimeError("simulated persist+reporting failure")

    try:
        orch.process_with_legacy_batch(
            job=job,
            aisle=aisle,
            assets=[asset],
            batch_runner=failing_runner,
            pipeline_enabled=True,
            orchestrator_enabled=True,
            is_cancelled=lambda: False,
            worker_token="w1",
        )
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True

    state = repos["state_repo"].get_by_job_and_asset(job.id, asset.id)  # type: ignore[union-attr]
    assert state is not None and state.status == JobAssetProcessingStatus.FAILED_TECHNICAL

    attempts = repos["attempt_repo"].list_by_job(job.id)  # type: ignore[union-attr]
    assert len(attempts) == 1
    assert attempts[0].status == ProcessingAttemptStatus.FAILED_TECHNICAL
    assert attempts[0].error_code == "BATCH_RUNNER_EXCEPTION"

    lease = repos["lease_repo"].get_by_job_strategy_scope(  # type: ignore[union-attr]
        job.id, "LEGACY_LLM", "AISLE_BATCH"
    )
    assert lease is not None and lease.status.value == "FAILED"


def test_recovery_closes_started_attempts() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    orch, repos = _build_orchestrator(clock, abandoned_processing_ttl_seconds=60)
    job = _job()
    asset = _asset("asset-1", now)
    orch.ensure_asset_states(job, [asset])

    state_repo = repos["state_repo"]
    attempt_repo = repos["attempt_repo"]
    stale_started = now - timedelta(seconds=120)

    state = state_repo.get_by_job_and_asset(job.id, asset.id)  # type: ignore[union-attr]
    assert state is not None
    state.status = JobAssetProcessingStatus.PROCESSING
    state.worker_token = "old-worker"
    state.started_at = stale_started
    state.updated_at = stale_started
    state_repo.save(state)  # type: ignore[union-attr]

    attempt = attempt_repo.create_next_attempt(  # type: ignore[union-attr]
        job_id=job.id,
        asset_id=asset.id,
        strategy="LEGACY_LLM",
        status=ProcessingAttemptStatus.STARTED,
        now=stale_started,
        worker_token="old-worker",
    )

    recovered_asset_ids = orch.recover_abandoned_processing(job.id)
    assert recovered_asset_ids == [asset.id]
    orch._close_started_attempts_for_assets(job.id, recovered_asset_ids, now)  # noqa: SLF001

    recovered_state = state_repo.get_by_job_and_asset(job.id, asset.id)  # type: ignore[union-attr]
    assert recovered_state is not None
    assert recovered_state.status == JobAssetProcessingStatus.PENDING

    closed_attempt = attempt_repo.get_by_id(attempt.id)  # type: ignore[union-attr]
    assert closed_attempt is not None
    assert closed_attempt.status == ProcessingAttemptStatus.FAILED_TECHNICAL


# ---------------------------------------------------------------------------
# AssetResultCoverageResolver
# ---------------------------------------------------------------------------


def test_coverage_resolver_resolved_from_result_evidence() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result_evidence_repo = MemoryResultEvidenceRepository()
    result_evidence_repo.save_many(
        [_result_evidence_row(job_id="job1", aisle_id="a1", asset_id="asset-1", has_valid_evidence=True, now=now)]
    )
    resolver = AssetResultCoverageResolver(
        result_evidence_repo=result_evidence_repo,
        evidence_repo=MemoryEvidenceRepository(),
        position_repo=MemoryPositionRepository(),
    )
    status = resolver.resolve(job_id="job1", aisle_id="a1", asset_id="asset-1")
    assert status == AssetResultCoverageStatus.RESOLVED


def test_coverage_resolver_resolved_from_position_evidence_link() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    position_repo = MemoryPositionRepository()
    position_repo.save(
        Position(
            id="p1",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            job_id="job1",
        )
    )
    evidence_repo = MemoryEvidenceRepository()
    evidence_repo.save(
        Evidence(
            id="e1",
            entity_type="position",
            entity_id="p1",
            type=EvidenceType.POSITION_CROP,
            storage_path="/e1.jpg",
            is_primary=True,
            source_asset_id="asset-1",
        )
    )
    resolver = AssetResultCoverageResolver(
        result_evidence_repo=MemoryResultEvidenceRepository(),
        evidence_repo=evidence_repo,
        position_repo=position_repo,
    )
    status = resolver.resolve(job_id="job1", aisle_id="a1", asset_id="asset-1")
    assert status == AssetResultCoverageStatus.RESOLVED


def test_coverage_resolver_unrecognized_when_other_assets_have_coverage() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result_evidence_repo = MemoryResultEvidenceRepository()
    result_evidence_repo.save_many(
        [_result_evidence_row(job_id="job1", aisle_id="a1", asset_id="asset-1", has_valid_evidence=True, now=now)]
    )
    resolver = AssetResultCoverageResolver(
        result_evidence_repo=result_evidence_repo,
        evidence_repo=MemoryEvidenceRepository(),
        position_repo=MemoryPositionRepository(),
    )
    status = resolver.resolve(job_id="job1", aisle_id="a1", asset_id="asset-2")
    assert status == AssetResultCoverageStatus.UNRECOGNIZED


def test_coverage_resolver_pending_reconciliation_when_no_signal_at_all() -> None:
    resolver = AssetResultCoverageResolver(
        result_evidence_repo=MemoryResultEvidenceRepository(),
        evidence_repo=MemoryEvidenceRepository(),
        position_repo=MemoryPositionRepository(),
    )
    status = resolver.resolve(job_id="job1", aisle_id="a1", asset_id="asset-1")
    assert status == AssetResultCoverageStatus.PENDING_RECONCILIATION


# ---------------------------------------------------------------------------
# AisleIdentificationConfigurationQuery.for_aisles
# ---------------------------------------------------------------------------


def test_for_aisles_single_inventory_load() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class CountingInventoryRepo(MemoryInventoryRepository):
        def __init__(self) -> None:
            super().__init__()
            self.get_by_id_calls = 0

        def get_by_id(self, inventory_id: str) -> Inventory | None:
            self.get_by_id_calls += 1
            return super().get_by_id(inventory_id)

    inventory_repo = CountingInventoryRepo()
    inventory_repo.save(
        Inventory(
            id="inv1",
            name="Inv 1",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
        )
    )

    from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
    from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository

    query = AisleIdentificationConfigurationQuery(
        aisle_repo=MemoryAisleRepository(),
        inventory_repo=inventory_repo,
        client_repo=MemoryClientRepository(),
    )
    aisles = [
        _aisle(now, aisle_id="a1", inventory_id="inv1"),
        _aisle(now, aisle_id="a2", inventory_id="inv1"),
        _aisle(now, aisle_id="a3", inventory_id="inv1"),
    ]
    result = query.for_aisles(aisles)
    assert set(result.keys()) == {"a1", "a2", "a3"}
    assert inventory_repo.get_by_id_calls == 1
