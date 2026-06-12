"""Authoritative finalization stage evidence — Phase 3.3."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FinalizationStage(str, Enum):
    DOMAIN_RESULTS = "domain_results"
    REQUIRED_ARTIFACTS = "required_artifacts"
    JOB_TERMINALIZATION = "job_terminalization"
    OPERATIONAL_PROMOTION = "operational_promotion"
    AISLE_RECONCILIATION = "aisle_reconciliation"
    INVENTORY_RECONCILIATION = "inventory_reconciliation"


class StageStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    VERIFICATION_REQUIRED = "verification_required"
    UNKNOWN = "unknown"


class EvidenceLevel(str, Enum):
    TRANSACTIONAL = "transactional"
    CONFIRMED = "confirmed"
    POSITIVE_EVIDENCE_ONLY = "positive_evidence_only"
    DERIVED = "derived"
    VERIFICATION_REQUIRED = "verification_required"
    UNKNOWN = "unknown"


class DomainSnapshotVerdict(str, Enum):
    CONFIRMED_COMPLETE = "confirmed_complete"
    CONFIRMED_EMPTY_VALID = "confirmed_empty_valid"
    INCOMPLETE = "incomplete"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class ArtifactVerificationVerdict(str, Enum):
    CONFIRMED = "confirmed"
    MISSING = "missing"
    MISMATCH = "mismatch"
    UNVERIFIABLE = "unverifiable"


class FinalizationAssessmentOutcome(str, Enum):
    COMPLETE = "complete"
    FAILED_BEFORE_DOMAIN_COMMIT = "failed_before_domain_commit"
    DOMAIN_COMMITTED_ARTIFACTS_MISSING = "domain_committed_artifacts_missing"
    ARTIFACTS_COMPLETE_TERMINALIZATION_MISSING = "artifacts_complete_terminalization_missing"
    TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING = "technically_succeeded_reconciliation_pending"
    VERIFICATION_REQUIRED = "verification_required"
    INCONSISTENT = "inconsistent"


# Ordered pipeline stages for assessment traversal.
FINALIZATION_STAGE_ORDER: tuple[FinalizationStage, ...] = (
    FinalizationStage.DOMAIN_RESULTS,
    FinalizationStage.REQUIRED_ARTIFACTS,
    FinalizationStage.JOB_TERMINALIZATION,
    FinalizationStage.OPERATIONAL_PROMOTION,
    FinalizationStage.AISLE_RECONCILIATION,
    FinalizationStage.INVENTORY_RECONCILIATION,
)


@dataclass
class FinalizationStageRecord:
    job_id: str
    stage: FinalizationStage
    status: StageStatus
    evidence_level: EvidenceLevel
    completed_at: datetime | None = None
    verified_at: datetime | None = None
    verification_source: str | None = None
    attempt_count: int = 0
    last_error_code: str | None = None
    last_error_metadata: dict[str, Any] | None = field(default=None)
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class StageAssessment:
    stage: FinalizationStage
    status: StageStatus
    evidence_level: EvidenceLevel
    completed_at: datetime | None
    verification_required: bool
    last_error_code: str | None = None


@dataclass(frozen=True)
class FinalizationAssessment:
    job_id: str
    outcome: FinalizationAssessmentOutcome
    technical_result_status: str
    finalization_status: str
    last_confirmed_stage: FinalizationStage | None
    next_required_stage: FinalizationStage | None
    recovery_candidate: bool
    blocking_reason: str | None
    stages: dict[str, StageAssessment]
