"""Targeted manual finalization recovery — Phase 3.4."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.domain.jobs.finalization_evidence import (
    FinalizationAssessment,
    FinalizationStage,
)


class RecoveryOperation(str, Enum):
    VERIFY = "verify"
    REPUBLISH_ARTIFACTS = "republish_artifacts"
    TERMINALIZE = "terminalize"
    PROMOTE = "promote"
    RECONCILE_AISLE = "reconcile_aisle"
    RECONCILE_INVENTORY = "reconcile_inventory"
    RESUME = "resume"


class RecoveryOutcome(str, Enum):
    RECOVERED = "recovered"
    ALREADY_COMPLETE = "already_complete"
    ALREADY_OPERATIONAL = "already_operational"
    ALREADY_SUPERSEDED = "already_superseded"
    NOT_ELIGIBLE = "not_eligible"
    VERIFICATION_REQUIRED = "verification_required"
    SOURCE_UNAVAILABLE = "source_unavailable"
    CONCURRENCY_CONFLICT = "concurrency_conflict"
    INCONSISTENT = "inconsistent"
    FAILED = "failed"
    PARTIALLY_RECOVERED = "partially_recovered"


class RecoveryAttemptStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    REJECTED = "rejected"


class ArtifactRecoverySourceStatus(str, Enum):
    AVAILABLE_EXACT = "available_exact"
    AVAILABLE_RECONSTRUCTED = "available_reconstructed"
    NOT_AVAILABLE = "not_available"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class ArtifactRecoverySource:
    artifact_kind: str
    status: ArtifactRecoverySourceStatus
    run_dir: str | None = None
    local_path: str | None = None
    detail: str | None = None


@dataclass
class RecoveryAttemptRecord:
    id: str
    recovery_id: str
    job_id: str
    operation: RecoveryOperation
    status: RecoveryAttemptStatus
    started_at: datetime
    requested_by: str
    source: str
    initial_assessment_outcome: str
    initial_blocking_reason: str | None = None
    finished_at: datetime | None = None
    final_assessment_outcome: str | None = None
    final_blocking_reason: str | None = None
    error_code: str | None = None
    sanitized_error: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class RecoveryResult:
    job_id: str
    operation: RecoveryOperation
    outcome: RecoveryOutcome
    previous_assessment: FinalizationAssessment
    new_assessment: FinalizationAssessment
    stages_attempted: tuple[FinalizationStage, ...] = ()
    stages_completed: tuple[FinalizationStage, ...] = ()
    stages_skipped: tuple[FinalizationStage, ...] = ()
    error_code: str | None = None
    sanitized_message: str | None = None
    dry_run: bool = False
    recovery_id: str | None = None
    eligible_operations: tuple[RecoveryOperation, ...] = ()
    blocked_operations: tuple[RecoveryOperation, ...] = ()


@dataclass(frozen=True)
class RecoveryDryRunPlan:
    job_id: str
    operation: RecoveryOperation
    current_assessment: FinalizationAssessment
    eligible_operations: tuple[RecoveryOperation, ...]
    blocked_operations: tuple[RecoveryOperation, ...]
    predicted_next_stage: FinalizationStage | None
    artifact_sources: tuple[ArtifactRecoverySource, ...] = field(default_factory=tuple)
