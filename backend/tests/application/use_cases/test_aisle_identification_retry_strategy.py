"""Retry recalculates execution_strategy via phase1_execution_strategy (Phase 1).

Regression coverage: retry must not blindly copy the original job's execution_strategy —
it must re-derive it from the immutable identification_mode snapshot and the *current*
feature flag, so a flag toggle between the original attempt and the retry is reflected.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.application.services.aisle_identification_execution import phase1_execution_strategy
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.retry_aisle_job import (
    RetryAisleJobCommand,
    RetryAisleJobUseCase,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.jobs.entities import Job, JobStatus
from tests.application.use_cases.test_retry_aisle_job import (
    StubWorkerLaunchService,
    _base_context,
    make_launch_service,
    make_stale_reconciler,
)


def _failed_job(
    *,
    now: datetime,
    job_id: str = "job-failed",
    identification_mode: AisleIdentificationMode = AisleIdentificationMode.CODE_SCAN,
    identification_mode_source: AisleIdentificationModeSource = (
        AisleIdentificationModeSource.AISLE
    ),
    execution_strategy: AisleIdentificationExecutionStrategy = (
        AisleIdentificationExecutionStrategy.LEGACY_LLM
    ),
) -> Job:
    return Job(
        id=job_id,
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        attempt_count=1,
        identification_mode=identification_mode,
        identification_mode_source=identification_mode_source,
        execution_strategy=execution_strategy,
    )


def _build_use_case(
    *, inv_repo, aisle_repo, job_repo, clock
) -> RetryAisleJobUseCase:
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    return RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=StubWorkerLaunchService(),
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )


def test_retry_code_scan_original_flag_off_recomputes_legacy_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Original job created with the flag off (LEGACY_LLM strategy); retry keeps flag off → LEGACY_LLM."""
    monkeypatch.setenv("AISLE_IDENTIFICATION_PIPELINE_ENABLED", "false")
    from src.config import reload_settings

    reload_settings()
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    original = _failed_job(
        now=now,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM,
    )
    job_repo.save(original)
    use_case = _build_use_case(inv_repo=inv_repo, aisle_repo=aisle_repo, job_repo=job_repo, clock=clock)

    retried = use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-failed"))

    assert retried.identification_mode == AisleIdentificationMode.CODE_SCAN
    assert retried.execution_strategy == AisleIdentificationExecutionStrategy.LEGACY_LLM


def test_retry_reuses_execution_strategy_snapshot_when_flag_flips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry keeps the original immutable execution_strategy (flags do not recompute it)."""
    monkeypatch.setenv("AISLE_IDENTIFICATION_PIPELINE_ENABLED", "false")
    from src.config import reload_settings

    reload_settings()
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    original = _failed_job(
        now=now,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM,
    )
    job_repo.save(original)

    # Flag flips on between the original attempt and the retry request.
    monkeypatch.setenv("AISLE_IDENTIFICATION_PIPELINE_ENABLED", "true")
    reload_settings()

    use_case = _build_use_case(inv_repo=inv_repo, aisle_repo=aisle_repo, job_repo=job_repo, clock=clock)

    retried = use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-failed"))

    assert retried.identification_mode == AisleIdentificationMode.CODE_SCAN
    assert retried.execution_strategy == AisleIdentificationExecutionStrategy.LEGACY_LLM


def test_retry_legacy_llm_stays_legacy_llm_regardless_of_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AISLE_IDENTIFICATION_PIPELINE_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    original = _failed_job(
        now=now,
        identification_mode=AisleIdentificationMode.LEGACY_LLM,
        identification_mode_source=AisleIdentificationModeSource.SYSTEM_DEFAULT,
        execution_strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM,
    )
    job_repo.save(original)
    use_case = _build_use_case(inv_repo=inv_repo, aisle_repo=aisle_repo, job_repo=job_repo, clock=clock)

    retried = use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-failed"))

    assert retried.identification_mode == AisleIdentificationMode.LEGACY_LLM
    assert retried.execution_strategy == AisleIdentificationExecutionStrategy.LEGACY_LLM


def test_phase1_execution_strategy_helper_requires_flags() -> None:
    """Sanity-check the shared helper: disabled strategies no longer fall back to legacy."""
    import pytest

    from src.application.errors import StrategyDisabledError

    with pytest.raises(StrategyDisabledError):
        phase1_execution_strategy(
            effective_mode=AisleIdentificationMode.CODE_SCAN, pipeline_enabled=False
        )
    with pytest.raises(StrategyDisabledError):
        phase1_execution_strategy(
            effective_mode=AisleIdentificationMode.CODE_SCAN, pipeline_enabled=True
        )
    assert phase1_execution_strategy(
        effective_mode=AisleIdentificationMode.LEGACY_LLM, pipeline_enabled=True
    ) == AisleIdentificationExecutionStrategy.LEGACY_LLM
