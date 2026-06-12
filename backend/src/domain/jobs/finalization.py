"""Job finalization state model — Phase 3.2."""

from __future__ import annotations

from enum import Enum


class FinalizationStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELED = "canceled"


class CurrentFinalizationStep(str, Enum):
    """Step currently executing (not yet completed)."""

    PERSIST_DOMAIN_RESULTS = "persist_domain_results"
    PUBLISH_ARTIFACTS = "publish_artifacts"
    TERMINALIZE_JOB = "terminalize_job"
    PROMOTE_OPERATIONAL_RESULT = "promote_operational_result"
    UPDATE_AISLE = "update_aisle"
    RECONCILE_INVENTORY = "reconcile_inventory"


class LastCompletedFinalizationStep(str, Enum):
    """Last step that completed successfully."""

    NONE = "none"
    DOMAIN_RESULTS_PERSISTED = "domain_results_persisted"
    ARTIFACTS_PUBLISHED = "artifacts_published"
    JOB_TERMINALIZED = "job_terminalized"
    OPERATIONAL_RESULT_PROMOTED = "operational_result_promoted"
    AISLE_UPDATED = "aisle_updated"
    INVENTORY_RECONCILED = "inventory_reconciled"


class FinalizationErrorCode(str, Enum):
    DOMAIN_PERSISTENCE_FAILED = "DOMAIN_PERSISTENCE_FAILED"
    ARTIFACT_STORE_UNAVAILABLE = "ARTIFACT_STORE_UNAVAILABLE"
    ARTIFACT_SOURCE_STAGING_FAILED = "ARTIFACT_SOURCE_STAGING_FAILED"
    ARTIFACT_PUBLISH_FAILED = "ARTIFACT_PUBLISH_FAILED"
    ARTIFACT_PUBLISH_PARTIAL = "ARTIFACT_PUBLISH_PARTIAL"
    JOB_TERMINALIZATION_FAILED = "JOB_TERMINALIZATION_FAILED"
    OPERATIONAL_PROMOTION_FAILED = "OPERATIONAL_PROMOTION_FAILED"
    AISLE_RECONCILIATION_FAILED = "AISLE_RECONCILIATION_FAILED"
    INVENTORY_RECONCILIATION_FAILED = "INVENTORY_RECONCILIATION_FAILED"
    FINALIZATION_CANCELED = "FINALIZATION_CANCELED"
    FINALIZATION_METADATA_WRITE_FAILED = "FINALIZATION_METADATA_WRITE_FAILED"


# Promotion outcomes that represent hard failures (not benign stale/already).
_PROMOTION_HARD_FAILURES = frozenset(
    {
        "rejected_invalid_status",
        "rejected_wrong_aisle",
        "rejected_invalid_job_type",
        "rejected_job_not_found",
        "rejected_aisle_not_found",
        "conflict",
    }
)


def is_hard_promotion_failure(outcome_value: str) -> bool:
    return outcome_value in _PROMOTION_HARD_FAILURES
