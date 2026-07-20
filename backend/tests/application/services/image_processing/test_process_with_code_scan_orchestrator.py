"""Unit tests for AisleProcessingOrchestrator.process_with_code_scan (Phase 3)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.image_processing.aisle_processing_orchestrator import (
    AisleProcessingOrchestrator,
)
from src.application.services.image_processing.asset_result_coverage_resolver import (
    AssetResultCoverageResolver,
)
from src.application.services.image_processing.image_processing_orchestrator import (
    ImageProcessingOrchestrator,
)
from src.application.services.image_processing.legacy_llm_processing_strategy import (
    LegacyLlmProcessingStrategy,
)
from src.application.services.image_processing.processing_result_persister import (
    PersistOutcome,
    PersistSkipReason,
)
from src.application.services.image_processing.processing_strategy_resolver import (
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
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingStatus,
)
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_batch_processing_attempt_repository import (
    MemoryBatchProcessingAttemptRepository,
)
from src.infrastructure.repositories.memory_evidence_repository import (
    MemoryEvidenceRepository,
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


class FakeCodeScanStrategy:
    strategy_key = "CODE_SCAN"

    def __init__(self, results_by_asset: dict[str, ImageResultStatus]) -> None:
        self._results = results_by_asset

    def process(self, context, asset) -> ImageProcessingResult:
        status = self._results[asset.id]
        return ImageProcessingResult(
            job_id=context.job_id,
            asset_id=context.asset_id,
            status=status,
            processing_mode="CODE_SCAN",
            resolved_by="CODE_SCAN",
            internal_code="ABC" if status is ImageResultStatus.RESOLVED_INTERNAL else None,
            quantity=5.0 if status is ImageResultStatus.RESOLVED_INTERNAL else None,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )


class FakePersister:
    def __init__(self) -> None:
        self.persisted: list[str] = []

    def persist(self, *, result, inventory_id, aisle_id) -> PersistOutcome:
        self.persisted.append(result.asset_id)
        return PersistOutcome(persisted=True, position_id=f"pos-{result.asset_id}")


class FakeOutcomePersister:
    """Persister that returns a caller-supplied fixed outcome (to test honoring)."""

    def __init__(self, outcome: PersistOutcome) -> None:
        self._outcome = outcome
        self.calls: list[str] = []

    def persist(self, *, result, inventory_id, aisle_id) -> PersistOutcome:
        self.calls.append(result.asset_id)
        return self._outcome


def _job() -> Job:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Job(
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
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        provider_name=None,
        model_name=None,
        prompt_key=None,
    )


def _aisle(now: datetime) -> Aisle:
    return Aisle(
        id="a1",
        inventory_id="inv1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


def _asset(asset_id: str, now: datetime) -> SourceAsset:
    return SourceAsset(
        id=asset_id,
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename=f"{asset_id}.jpg",
        storage_path=f"/{asset_id}.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )


def _build(strategy, persister, *, concurrency: int = 1):
    clock = FixedClock(datetime(2026, 1, 2, tzinfo=timezone.utc))
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    lease_repo = MemoryJobProcessingLeaseRepository()
    batch_attempt_repo = MemoryBatchProcessingAttemptRepository()
    result_evidence_repo = MemoryResultEvidenceRepository()
    evidence_repo = MemoryEvidenceRepository()
    position_repo = MemoryPositionRepository()
    image_orch = ImageProcessingOrchestrator(state_repo, attempt_repo, clock, attempts_enabled=True)
    orch = AisleProcessingOrchestrator(
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        lease_repo=lease_repo,
        batch_attempt_repo=batch_attempt_repo,
        clock=clock,
        image_orchestrator=image_orch,
        strategy_resolver=ProcessingStrategyResolver(),
        legacy_strategy=LegacyLlmProcessingStrategy(),
        coverage_resolver=AssetResultCoverageResolver(
            result_evidence_repo=result_evidence_repo,
            evidence_repo=evidence_repo,
            position_repo=position_repo,
        ),
        attempts_enabled=True,
        code_scan_strategy=strategy,
        result_persister=persister,
        code_scan_concurrency=concurrency,
    )
    return orch, state_repo


def test_mixed_outcomes_persist_only_resolved() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    strategy = FakeCodeScanStrategy(
        {
            "s1": ImageResultStatus.RESOLVED_INTERNAL,
            "s2": ImageResultStatus.UNRECOGNIZED,
            "s3": ImageResultStatus.PENDING_MANUAL_REVIEW,
        }
    )
    persister = FakePersister()
    orch, state_repo = _build(strategy, persister)
    assets = [_asset("s1", now), _asset("s2", now), _asset("s3", now)]

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(now),
        assets=assets,
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert outcome.ok is True
    assert outcome.cancelled is False
    assert outcome.strategy_key == "CODE_SCAN"
    assert outcome.progress.resolved == 1
    assert outcome.progress.unrecognized == 1
    assert outcome.progress.manual_review == 1
    assert persister.persisted == ["s1"]


def test_cancel_before_processing_marks_cancelled() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    strategy = FakeCodeScanStrategy({"s1": ImageResultStatus.RESOLVED_INTERNAL})
    persister = FakePersister()
    orch, _ = _build(strategy, persister)

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(now),
        assets=[_asset("s1", now)],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: True,
        worker_token="w1",
    )

    assert outcome.cancelled is True
    assert outcome.ok is False
    assert persister.persisted == []


def test_persist_not_honored_becomes_failed_not_resolved() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    strategy = FakeCodeScanStrategy({"s1": ImageResultStatus.RESOLVED_INTERNAL})
    persister = FakeOutcomePersister(
        PersistOutcome(
            persisted=False,
            reconciled=False,
            skipped_reason=PersistSkipReason.CONCURRENCY_CONFLICT,
        )
    )
    orch, state_repo = _build(strategy, persister)

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(now),
        assets=[_asset("s1", now)],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert persister.calls == ["s1"]
    assert outcome.progress.resolved == 0
    assert outcome.progress.failed == 1
    state = state_repo.get_by_job_and_asset("job1", "s1")
    assert state.status is JobAssetProcessingStatus.FAILED_TECHNICAL


def test_persist_manual_result_exists_becomes_manual_review() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    strategy = FakeCodeScanStrategy({"s1": ImageResultStatus.RESOLVED_INTERNAL})
    persister = FakeOutcomePersister(
        PersistOutcome(
            persisted=False,
            reconciled=False,
            position_id="pos-existing",
            skipped_reason=PersistSkipReason.MANUAL_RESULT_EXISTS,
        )
    )
    orch, state_repo = _build(strategy, persister)

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(now),
        assets=[_asset("s1", now)],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert outcome.progress.resolved == 0
    assert outcome.progress.manual_review == 1
    state = state_repo.get_by_job_and_asset("job1", "s1")
    assert state.status is JobAssetProcessingStatus.PENDING_MANUAL_REVIEW


def test_persist_reconciled_keeps_resolved() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    strategy = FakeCodeScanStrategy({"s1": ImageResultStatus.RESOLVED_INTERNAL})
    persister = FakeOutcomePersister(
        PersistOutcome(
            persisted=False,
            reconciled=True,
            position_id="pos-existing",
            active_result_id="pos-existing",
            skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
        )
    )
    orch, state_repo = _build(strategy, persister)

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(now),
        assets=[_asset("s1", now)],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert outcome.progress.resolved == 1
    state = state_repo.get_by_job_and_asset("job1", "s1")
    assert state.status is JobAssetProcessingStatus.RESOLVED
    assert state.active_result_id == "pos-existing"


def test_missing_persister_raises_misconfigured() -> None:
    import pytest

    from src.application.errors import CodeScanPipelineMisconfiguredError

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    strategy = FakeCodeScanStrategy({"s1": ImageResultStatus.RESOLVED_INTERNAL})
    orch, _ = _build(strategy, None)

    with pytest.raises(CodeScanPipelineMisconfiguredError):
        orch.process_with_code_scan(
            job=_job(),
            aisle=_aisle(now),
            assets=[_asset("s1", now)],
            pipeline_enabled=True,
            orchestrator_enabled=True,
            is_cancelled=lambda: False,
            worker_token="w1",
        )


def test_concurrency_two_memory_processes_all() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = ["s1", "s2", "s3", "s4"]
    strategy = FakeCodeScanStrategy({i: ImageResultStatus.RESOLVED_INTERNAL for i in ids})
    persister = FakePersister()
    orch, state_repo = _build(strategy, persister, concurrency=2)

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(now),
        assets=[_asset(i, now) for i in ids],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert outcome.progress.resolved == 4
    assert sorted(persister.persisted) == ids


def test_concurrency_one_processes_all() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    strategy = FakeCodeScanStrategy(
        {"s1": ImageResultStatus.RESOLVED_INTERNAL, "s2": ImageResultStatus.RESOLVED_INTERNAL}
    )
    persister = FakePersister()
    orch, state_repo = _build(strategy, persister, concurrency=1)

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(now),
        assets=[_asset("s1", now), _asset("s2", now)],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert outcome.progress.resolved == 2
    assert sorted(persister.persisted) == ["s1", "s2"]


def test_ten_eligible_assets_must_start_processing() -> None:
    """Regression: assets_eligible=10 must not complete with assets_started=0."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = [f"s{i}" for i in range(10)]
    strategy = FakeCodeScanStrategy({aid: ImageResultStatus.RESOLVED_INTERNAL for aid in ids})
    persister = FakePersister()
    orch, _ = _build(strategy, persister)

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(now),
        assets=[_asset(aid, now) for aid in ids],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert outcome.assets_eligible == 10
    assert outcome.assets_started == 10
    assert outcome.progress.resolved == 10
    assert outcome.job_outcome.value == "SUCCEEDED"


def test_assets_started_exact_under_concurrent_stress() -> None:
    """assets_started must be exact with ThreadPoolExecutor (no GIL reliance)."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    n = 120
    ids = [f"s{i}" for i in range(n)]
    strategy = FakeCodeScanStrategy({aid: ImageResultStatus.RESOLVED_INTERNAL for aid in ids})
    persister = FakePersister()
    orch, _ = _build(strategy, persister, concurrency=8)

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(now),
        assets=[_asset(aid, now) for aid in ids],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert outcome.assets_eligible == n
    assert outcome.assets_started == n
    assert outcome.progress.resolved == n
    assert len(persister.persisted) == n
    assert outcome.job_outcome.value == "SUCCEEDED"
