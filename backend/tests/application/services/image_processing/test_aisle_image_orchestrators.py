"""Unit tests for Phase 2 strategy resolver and aisle/image orchestrators."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.image_processing.aisle_processing_orchestrator import (
    AisleProcessingOrchestrator,
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
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
    CONFIGURATION_SNAPSHOT_VERSION,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.image_processing.job_asset_processing_state import JobAssetProcessingStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)
from src.infrastructure.repositories.memory_processing_attempt_repository import (
    MemoryProcessingAttemptRepository,
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


def test_strategy_resolver_always_legacy_for_phase2_modes() -> None:
    resolver = ProcessingStrategyResolver()
    for mode in (
        AisleIdentificationMode.LEGACY_LLM,
        AisleIdentificationMode.CODE_SCAN,
        AisleIdentificationMode.INTERNAL_OCR,
    ):
        job = _job(identification_mode=mode)
        assert (
            resolver.resolve_strategy_key(
                job, pipeline_enabled=True, orchestrator_enabled=True
            )
            == STRATEGY_LEGACY_LLM
        )
        assert (
            resolver.resolve_strategy_key(
                job, pipeline_enabled=False, orchestrator_enabled=False
            )
            == STRATEGY_LEGACY_LLM
        )


def test_aisle_orchestrator_synthesizes_resolved_and_unrecognized() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    image_orch = ImageProcessingOrchestrator(
        state_repo, attempt_repo, clock, attempts_enabled=True
    )

    def runner(**_kwargs: object) -> LegacyBatchOutcome:
        return LegacyBatchOutcome(ok=True, assets_with_result=frozenset({"asset-1"}))

    orch = AisleProcessingOrchestrator(
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        clock=clock,
        image_orchestrator=image_orch,
        strategy_resolver=ProcessingStrategyResolver(),
        legacy_strategy=LegacyLlmProcessingStrategy(batch_runner=runner),
        attempts_enabled=True,
    )
    aisle = Aisle(
        id="a1",
        inventory_id="inv1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    assets = [
        SourceAsset(
            id="asset-1",
            aisle_id="a1",
            type=SourceAssetType.PHOTO,
            original_filename="a.jpg",
            storage_path="/a.jpg",
            mime_type="image/jpeg",
            uploaded_at=now,
        ),
        SourceAsset(
            id="asset-2",
            aisle_id="a1",
            type=SourceAssetType.PHOTO,
            original_filename="b.jpg",
            storage_path="/b.jpg",
            mime_type="image/jpeg",
            uploaded_at=now,
        ),
    ]
    out = orch.process_with_legacy_batch(
        job=_job(),
        aisle=aisle,
        assets=assets,
        runner_kwargs={},
        pipeline_enabled=True,
        orchestrator_enabled=True,
    )
    assert out.progress.total == 2
    assert out.progress.resolved == 1
    assert out.progress.unrecognized == 1
    s1 = state_repo.get_by_job_and_asset("job1", "asset-1")
    s2 = state_repo.get_by_job_and_asset("job1", "asset-2")
    assert s1 is not None and s1.status == JobAssetProcessingStatus.RESOLVED
    assert s2 is not None and s2.status == JobAssetProcessingStatus.UNRECOGNIZED
    attempts = attempt_repo.list_by_job("job1")
    assert len(attempts) == 2


def test_image_orchestrator_skips_already_resolved() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    image_orch = ImageProcessingOrchestrator(
        state_repo, attempt_repo, clock, attempts_enabled=True
    )
    orch = AisleProcessingOrchestrator(
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        clock=clock,
        image_orchestrator=image_orch,
        strategy_resolver=ProcessingStrategyResolver(),
        legacy_strategy=LegacyLlmProcessingStrategy(
            batch_runner=lambda **_k: LegacyBatchOutcome(ok=True, assets_with_result=frozenset())
        ),
        attempts_enabled=True,
    )
    job = _job()
    aisle = Aisle(
        id="a1",
        inventory_id="inv1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    asset = SourceAsset(
        id="asset-1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="a.jpg",
        storage_path="/a.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )
    orch.ensure_asset_states(job, [asset])
    state = state_repo.get_by_job_and_asset("job1", "asset-1")
    assert state is not None
    state.status = JobAssetProcessingStatus.RESOLVED
    state_repo.save(state)
    acquired = image_orch.acquire_for_processing(
        job_id="job1", asset_id="asset-1", strategy="LEGACY_LLM"
    )
    assert acquired is None


def test_try_acquire_race_only_one_wins() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    image_orch = ImageProcessingOrchestrator(
        state_repo, attempt_repo, clock, attempts_enabled=False
    )
    orch = AisleProcessingOrchestrator(
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        clock=clock,
        image_orchestrator=image_orch,
        strategy_resolver=ProcessingStrategyResolver(),
        legacy_strategy=LegacyLlmProcessingStrategy(),
        attempts_enabled=False,
    )
    job = _job()
    asset = SourceAsset(
        id="asset-1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="a.jpg",
        storage_path="/a.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )
    orch.ensure_asset_states(job, [asset])
    first = image_orch.acquire_for_processing(
        job_id="job1", asset_id="asset-1", strategy="LEGACY_LLM"
    )
    second = image_orch.acquire_for_processing(
        job_id="job1", asset_id="asset-1", strategy="LEGACY_LLM"
    )
    assert first is not None
    assert second is None
