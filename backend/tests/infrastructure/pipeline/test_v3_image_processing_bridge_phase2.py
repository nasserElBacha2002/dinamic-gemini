"""Phase 2 corrections — V3 bridge / executor semantics for legacy outcome propagation."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
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
    build_default_code_scan_persister,
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


def test_code_scan_persister_builder_propagates_enabled_materializer() -> None:
    materializer = MagicMock()
    container = MagicMock()
    container.get_position_materialization_service.return_value = materializer
    clock = MagicMock()

    persister = build_default_code_scan_persister(
        job_source_asset_repo=MagicMock(),
        source_asset_repo=MagicMock(),
        clock=clock,
        unit_of_work_factory=MagicMock(),
        position_detection_repo=MagicMock(),
        settings=SimpleNamespace(
            position_auto_materialization_enabled=True,
            position_flexible_validation_enabled=True,
            position_flexible_code_scan_enabled=True,
            position_flexible_vision_enabled=False,
        ),
        container=container,
    )

    assert persister._position_auto_materialization_enabled is True
    assert persister._flexible_code_scan_enabled is True
    assert persister._flexible_vision_enabled is False
    assert persister._position_materializer is materializer
    container.get_position_materialization_service.assert_called_once_with()


def test_vision_on_does_not_enable_code_scan_materialization_alone() -> None:
    """Vision channel ON must not imply CODE_SCAN flexible materialization."""
    materializer = MagicMock()
    container = MagicMock()
    container.get_position_materialization_service.return_value = materializer
    persister = build_default_code_scan_persister(
        job_source_asset_repo=MagicMock(),
        source_asset_repo=MagicMock(),
        clock=MagicMock(),
        unit_of_work_factory=MagicMock(),
        position_detection_repo=MagicMock(),
        settings=SimpleNamespace(
            position_auto_materialization_enabled=True,
            position_flexible_validation_enabled=True,
            position_flexible_code_scan_enabled=False,
            position_flexible_vision_enabled=True,
        ),
        container=container,
    )
    assert persister._position_auto_materialization_enabled is True
    assert persister._flexible_vision_enabled is True
    assert persister._flexible_code_scan_enabled is False
    assert persister._position_materializer is materializer
    # CODE_SCAN source → channel gate off
    code_scan_result = SimpleNamespace(vision_position_evidence=())
    assert persister._channel_materialization_enabled(code_scan_result) is False
    vision_result = SimpleNamespace(vision_position_evidence=(object(),))
    assert persister._channel_materialization_enabled(vision_result) is True


def test_code_scan_persister_builder_wires_materializer_when_auto_on() -> None:
    """Auto master wires materializer; channel flags stay independent."""
    container = MagicMock()
    materializer = MagicMock()
    container.get_position_materialization_service.return_value = materializer
    persister = build_default_code_scan_persister(
        job_source_asset_repo=MagicMock(),
        source_asset_repo=MagicMock(),
        clock=MagicMock(),
        unit_of_work_factory=MagicMock(),
        position_detection_repo=MagicMock(),
        settings=SimpleNamespace(
            position_auto_materialization_enabled=True,
            position_flexible_validation_enabled=False,
            position_flexible_code_scan_enabled=False,
            position_flexible_vision_enabled=False,
        ),
        container=container,
    )
    assert persister._position_auto_materialization_enabled is True
    assert persister._position_materializer is materializer
    container.get_position_materialization_service.assert_called_once_with()
    code_scan_result = SimpleNamespace(vision_position_evidence=())
    assert persister._channel_materialization_enabled(code_scan_result) is False


def test_code_scan_persister_builder_skips_materializer_when_auto_off() -> None:
    container = MagicMock()
    persister = build_default_code_scan_persister(
        job_source_asset_repo=MagicMock(),
        source_asset_repo=MagicMock(),
        clock=MagicMock(),
        unit_of_work_factory=MagicMock(),
        position_detection_repo=MagicMock(),
        settings=SimpleNamespace(
            position_auto_materialization_enabled=False,
            position_flexible_validation_enabled=True,
            position_flexible_code_scan_enabled=True,
            position_flexible_vision_enabled=True,
        ),
        container=container,
    )
    assert persister._position_auto_materialization_enabled is False
    assert persister._position_materializer is None
    container.get_position_materialization_service.assert_not_called()


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
