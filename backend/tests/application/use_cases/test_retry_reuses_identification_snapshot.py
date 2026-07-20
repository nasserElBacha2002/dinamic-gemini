"""Retry must reuse original identification snapshot (no flag re-interpretation)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.use_cases.aisles.retry_aisle_job import (
    RetryAisleJobCommand,
    RetryAisleJobUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.jobs.entities import Job, JobStatus


def test_retry_reuses_original_execution_strategy_and_engine_params() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    original = Job(
        id="job-old",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        identification_mode_source=AisleIdentificationModeSource.REQUEST,
        execution_strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM_TEMPORARY,
        engine_params_json={
            "identification_execution": {
                "requested_mode": "CODE_SCAN",
                "executed_strategy": "LEGACY_LLM_TEMPORARY",
                "reason": "CODE_SCAN_PROCESSING_ENABLED_FALSE",
            },
            "client_id": "client-1",
        },
        attempt_count=1,
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )

    job_repo = MagicMock()
    job_repo.get_by_id.return_value = original
    job_repo.get_latest_by_target.return_value = original

    aisle_repo = MagicMock()
    aisle_repo.get_by_id.return_value = aisle

    captured: dict = {}

    def _launch(**kwargs):
        captured.update(kwargs)
        return Job(
            id="job-new",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
            identification_mode=kwargs["identification_mode"],
            identification_mode_source=kwargs["identification_mode_source"],
            execution_strategy=kwargs["execution_strategy"],
            engine_params_json=kwargs.get("engine_params_json"),
            attempt_count=kwargs["attempt_count"],
            configuration_snapshot_version=kwargs["configuration_snapshot_version"],
        )

    launch = MagicMock()
    launch.create_and_launch_attempt.side_effect = _launch

    stale = MagicMock()
    stale.reconcile.side_effect = lambda job: job

    uc = RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=launch,
        stale_reconciler=stale,
    )
    result = uc.execute(
        RetryAisleJobCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="job-old")
    )
    assert result.id == "job-new"
    assert (
        captured["execution_strategy"]
        is AisleIdentificationExecutionStrategy.LEGACY_LLM_TEMPORARY
    )
    assert captured["engine_params_json"]["identification_execution"]["reason"] == (
        "CODE_SCAN_PROCESSING_ENABLED_FALSE"
    )
    assert captured["engine_params_json"]["client_id"] == "client-1"
