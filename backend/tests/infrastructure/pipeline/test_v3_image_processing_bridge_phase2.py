"""Phase 2 corrections — V3 bridge / executor semantics for legacy outcome propagation."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.application.errors import ImageProcessingRepositoryUnavailableError
from src.application.ports.image_processing_repositories import AssetProgressCounts
from src.application.services.image_processing.aisle_processing_orchestrator import (
    AisleOrchestratorOutcome,
)
from src.application.services.image_processing.legacy_llm_processing_strategy import (
    LegacyBatchOutcome,
)
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_image_processing_bridge import (
    build_default_aisle_processing_orchestrator,
)
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository


def _job(job_id: str = "job-1", status: JobStatus = JobStatus.RUNNING) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id=job_id,
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=status,
        payload_json={},
        created_at=now,
        updated_at=now,
        result_json={"costs": {"total": 1.5}, "provider": "x"},
    )


def test_build_default_require_sql_fails_fast_when_repos_missing() -> None:
    clock = MagicMock()
    clock.now.return_value = datetime.now(timezone.utc)
    with pytest.raises(ImageProcessingRepositoryUnavailableError) as exc:
        build_default_aisle_processing_orchestrator(
            clock,
            attempts_enabled=True,
            state_repo=None,
            attempt_repo=None,
            lease_repo=None,
            batch_attempt_repo=None,
            result_evidence_repo=MagicMock(),
            evidence_repo=MagicMock(),
            position_repo=MagicMock(),
            require_sql=True,
        )
    assert "require_sql=True" in str(exc.value)


def test_merge_result_json_preserves_sibling_keys() -> None:
    repo = MemoryJobRepository()
    job = _job()
    repo.save(job)
    repo.merge_result_json(
        job.id,
        {"asset_progress": {"total": 2, "resolved": 1, "pending": 1}},
    )
    refreshed = repo.get_by_id(job.id)
    assert refreshed is not None
    assert refreshed.result_json is not None
    assert refreshed.result_json["costs"] == {"total": 1.5}
    assert refreshed.result_json["provider"] == "x"
    assert refreshed.result_json["asset_progress"]["total"] == 2


def test_legacy_outcome_ok_false_is_not_success() -> None:
    """Document the contract the executor must honor after orchestration."""
    outcome = AisleOrchestratorOutcome(
        legacy=LegacyBatchOutcome(ok=False, error_message="provider_failed"),
        progress=AssetProgressCounts(total=1, failed=1),
        strategy_key="LEGACY_LLM",
    )
    assert outcome.legacy.ok is False
    assert not outcome.legacy.skipped_busy


def test_legacy_outcome_skipped_busy_is_not_success() -> None:
    outcome = AisleOrchestratorOutcome(
        legacy=LegacyBatchOutcome(
            ok=False, error_message="BATCH_LEASE_NOT_ACQUIRED", skipped_busy=True
        ),
        progress=AssetProgressCounts(total=1, pending=1),
        strategy_key="LEGACY_LLM",
    )
    assert outcome.legacy.ok is False
    assert outcome.legacy.skipped_busy is True


def test_run_orchestrated_passes_batch_runner_without_private_mutation() -> None:
    from src.infrastructure.pipeline.v3_image_processing_bridge import (
        run_orchestrated_legacy_batch,
    )

    orch = MagicMock()
    orch.process_with_legacy_batch.return_value = AisleOrchestratorOutcome(
        legacy=LegacyBatchOutcome(ok=True),
        progress=AssetProgressCounts(),
        strategy_key="LEGACY_LLM",
    )
    runner = MagicMock(return_value=LegacyBatchOutcome(ok=True))
    job = _job()
    aisle = MagicMock()
    assets: list = []

    out = run_orchestrated_legacy_batch(
        orchestrator=orch,
        job=job,
        aisle=aisle,
        assets=assets,
        pipeline_enabled=False,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
        batch_runner=runner,
    )
    assert out.legacy.ok is True
    orch.process_with_legacy_batch.assert_called_once()
    kwargs = orch.process_with_legacy_batch.call_args.kwargs
    assert kwargs["batch_runner"] is runner
    assert not hasattr(orch, "_legacy") or orch._legacy is not runner
