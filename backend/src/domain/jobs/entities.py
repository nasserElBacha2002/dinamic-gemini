"""
Job domain entity — v3.0 (Documento técnico §7.8).

Technical work item associated with an aisle. Distinct from src/jobs (queue/store implementation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.domain.aisle_identification.modes import (
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationStatus,
    LastCompletedFinalizationStep,
)


class JobStatus(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    # Cancellation-related states — Stage 6:
    # - CANCEL_REQUESTED: operator requested cancellation; job may still be running.
    # - CANCELED: job observed cancellation and stopped cooperatively (no final report).
    # - TIMED_OUT: reserved for future timeout handling (not used in v3.1.2 Stage 6).
    CANCEL_REQUESTED = "cancel_requested"
    CANCELED = "canceled"
    TIMED_OUT = "timed_out"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    target_type: str
    target_id: str
    job_type: str
    status: JobStatus
    payload_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    result_json: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    current_stage: str | None = None
    current_substep: str | None = None
    current_step_started_at: datetime | None = None
    attempt_count: int = 1
    # Immediate previous attempt in a linear retry chain. Null on the original attempt.
    retry_of_job_id: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    execution_id: str | None = None
    # Phase 1 — transitional indexed metadata for future multi-provider work; not a runtime provider abstraction.
    provider_name: str | None = None
    model_name: str | None = None
    prompt_key: str | None = None
    engine_params_json: dict[str, Any] | None = None
    #: Resolved prompt profile version / schema tag for audit (e.g. ``global_v21@v2.1``).
    prompt_version: str | None = None
    # Phase 1 aisle identification — immutable snapshot at job creation (do not re-resolve).
    identification_mode: AisleIdentificationMode = AisleIdentificationMode.LEGACY_LLM
    identification_mode_source: AisleIdentificationModeSource = (
        AisleIdentificationModeSource.SYSTEM_DEFAULT
    )
    configuration_snapshot_version: int = CONFIGURATION_SNAPSHOT_VERSION
    #: Actual worker path (Phase 1: LEGACY_LLM or LEGACY_LLM_TEMPORARY).
    execution_strategy: AisleIdentificationExecutionStrategy = (
        AisleIdentificationExecutionStrategy.LEGACY_LLM
    )
    # Phase 3.2 — explicit finalization progress (distinct from pipeline current_stage).
    finalization_status: FinalizationStatus = FinalizationStatus.NOT_STARTED
    current_finalization_step: CurrentFinalizationStep | None = None
    last_completed_finalization_step: LastCompletedFinalizationStep = (
        LastCompletedFinalizationStep.NONE
    )
    finalization_error_code: str | None = None
    finalization_error_metadata: dict[str, Any] | None = field(default=None)
    finalization_started_at: datetime | None = None
    finalization_completed_at: datetime | None = None
    domain_persisted_at: datetime | None = None
    artifacts_published_at: datetime | None = None
