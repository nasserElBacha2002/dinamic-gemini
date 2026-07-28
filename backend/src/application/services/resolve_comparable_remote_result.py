"""Resolve a comparable remote result for one preliminary detection (asset-mapped)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src.application.services.preliminary_detection_compare import (
    normalize_code,
    normalize_quantity,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)
from src.domain.jobs.entities import JobStatus

REASON_NO_ASSET_MAPPING = "NOT_COMPARABLE_NO_ASSET_MAPPING"
REASON_GLOBAL_BATCH = "NOT_COMPARABLE_GLOBAL_BATCH"
REASON_MULTIPLE_REMOTE = "NOT_COMPARABLE_MULTIPLE_REMOTE_RESULTS"
REASON_MISSING_REMOTE = "NOT_COMPARABLE_MISSING_REMOTE_EVIDENCE"
REASON_VERSION_UNKNOWN = "NOT_COMPARABLE_VERSION_UNKNOWN"
REASON_REMOTE_NOT_TERMINAL = "NOT_COMPARABLE_REMOTE_NOT_TERMINAL"
REASON_JOB_NOT_TERMINAL = "NOT_COMPARABLE_JOB_NOT_TERMINAL"
REASON_LOCAL_NOT_TERMINAL = "NOT_COMPARABLE_LOCAL_NOT_TERMINAL"
REASON_JOB_FAILED = "NOT_COMPARABLE_JOB_FAILED"
REASON_JOB_CANCELED = "NOT_COMPARABLE_JOB_CANCELED"
REASON_JOB_TIMED_OUT = "NOT_COMPARABLE_JOB_TIMED_OUT"
REASON_ASSET_NOT_IN_SNAPSHOT = "NOT_COMPARABLE_ASSET_NOT_IN_SNAPSHOT"

_TERMINAL_ASSET_STATUSES = {
    JobAssetProcessingStatus.RESOLVED,
    JobAssetProcessingStatus.UNRECOGNIZED,
    JobAssetProcessingStatus.FAILED_TECHNICAL,
    JobAssetProcessingStatus.PENDING_MANUAL_REVIEW,
    JobAssetProcessingStatus.CANCELLED,
}

_ATTEMPT_RESULT_STATUSES = {
    ProcessingAttemptStatus.SUCCEEDED,
    ProcessingAttemptStatus.UNRECOGNIZED,
    ProcessingAttemptStatus.INVALID,
}

_LOCAL_TERMINAL = {
    "RESOLVED",
    "UNRESOLVED",
    "INVALID",
    "AMBIGUOUS",
    "FAILED",
    "DETECTED_UNVERIFIED",
}

_AUTHORITATIVE_JOB = {JobStatus.SUCCEEDED}


@dataclass(frozen=True)
class ComparableRemoteResult:
    remote_result_id: str
    status: str
    internal_code: str | None
    quantity: int | None
    ambiguous: bool
    completed_at: datetime | None
    pipeline_version: str | None
    strategy: str | None
    fingerprint: str


@dataclass(frozen=True)
class NotComparable:
    reason: str
    retryable: bool = False


def extract_normalized_code_quantity(
    normalized: dict | None,
) -> tuple[str | None, int | None]:
    if not isinstance(normalized, dict):
        return None, None
    code = normalized.get("internal_code")
    if code is None:
        code = normalized.get("code")
    qty = normalized.get("quantity")
    return normalize_code(str(code) if code is not None else None), normalize_quantity(
        qty if isinstance(qty, (int, float)) else None
    )


def remote_semantic_tuple(attempt: ProcessingAttempt) -> tuple[str | None, int | None, str]:
    code, qty = extract_normalized_code_quantity(attempt.normalized_result)
    status = attempt.status.value if hasattr(attempt.status, "value") else str(attempt.status)
    return (code, qty, status)


def fingerprint_from_tuple(t: tuple[str | None, int | None, str], attempt_id: str) -> str:
    code, qty, status = t
    return f"{status}|{code or ''}|{qty if qty is not None else ''}|{attempt_id}"


def _strategy_is_global_batch(strategy: str | None) -> bool:
    if not strategy:
        return False
    s = strategy.upper()
    return "GLOBAL_BATCH" in s or s == "GLOBAL_EXTERNAL_FALLBACK" or "GLOBAL_FALLBACK" in s


def job_result_authoritative(job_status: JobStatus) -> bool:
    return job_status in _AUTHORITATIVE_JOB


def job_not_authoritative_reason(job_status: JobStatus) -> str | None:
    if job_status is JobStatus.FAILED:
        return REASON_JOB_FAILED
    if job_status is JobStatus.CANCELED:
        return REASON_JOB_CANCELED
    if job_status is JobStatus.TIMED_OUT:
        return REASON_JOB_TIMED_OUT
    return None


class ResolveComparableRemoteResult:
    """Map preliminary → asset_id → job asset state + attempts. Never match by order."""

    def execute(
        self,
        *,
        local_status: str,
        local_parser_version: str | None,
        local_detector_version: str | None,
        job_terminal: bool,
        job_status: JobStatus,
        asset_in_job_snapshot: bool,
        state: JobAssetProcessingState | None,
        attempts: Sequence[ProcessingAttempt],
        remote_pipeline_version: str | None,
    ) -> ComparableRemoteResult | NotComparable:
        if (local_status or "").upper() not in _LOCAL_TERMINAL:
            return NotComparable(REASON_LOCAL_NOT_TERMINAL, retryable=False)

        if not (local_parser_version or "").strip() or not (local_detector_version or "").strip():
            return NotComparable(REASON_VERSION_UNKNOWN, retryable=False)

        if not (remote_pipeline_version or "").strip():
            return NotComparable(REASON_VERSION_UNKNOWN, retryable=False)

        if not job_terminal:
            return NotComparable(REASON_JOB_NOT_TERMINAL, retryable=True)

        bad = job_not_authoritative_reason(job_status)
        if bad is not None or not job_result_authoritative(job_status):
            return NotComparable(bad or REASON_JOB_FAILED, retryable=False)

        if not asset_in_job_snapshot:
            return NotComparable(REASON_ASSET_NOT_IN_SNAPSHOT, retryable=False)

        if state is None:
            return NotComparable(REASON_NO_ASSET_MAPPING, retryable=True)

        if state.status not in _TERMINAL_ASSET_STATUSES:
            return NotComparable(REASON_REMOTE_NOT_TERMINAL, retryable=True)

        final_is_global = _strategy_is_global_batch(state.last_strategy)
        logical = [a for a in attempts if a.logical_asset_attempt]
        result_attempts = [a for a in logical if a.status in _ATTEMPT_RESULT_STATUSES]

        if final_is_global:
            # Authoritative GLOBAL_BATCH: only structured global attempts — never prior CODE_SCAN.
            global_attempts = [
                a
                for a in result_attempts
                if _strategy_is_global_batch(a.strategy)
                or (a.execution_scope or "").upper() == "AISLE_BATCH"
                or a.parent_batch_attempt_id
            ]
            if not global_attempts:
                return NotComparable(REASON_GLOBAL_BATCH, retryable=False)
            result_attempts = global_attempts

        if not result_attempts:
            if final_is_global:
                return NotComparable(REASON_GLOBAL_BATCH, retryable=False)
            return NotComparable(REASON_MISSING_REMOTE, retryable=True)

        # Distinct semantic results (code + quantity + status); identical retries dedupe.
        unique: dict[tuple[str | None, int | None, str], ProcessingAttempt] = {}
        for a in result_attempts:
            key = remote_semantic_tuple(a)
            unique[key] = a
        if len(unique) > 1:
            return NotComparable(REASON_MULTIPLE_REMOTE, retryable=False)

        chosen = next(iter(unique.values()))
        code, qty = extract_normalized_code_quantity(chosen.normalized_result)
        status = chosen.status.value if hasattr(chosen.status, "value") else str(chosen.status)
        remote_ambiguous = False
        validation = chosen.validation_result if isinstance(chosen.validation_result, dict) else {}
        candidates = validation.get("candidates") if isinstance(validation, dict) else None
        if isinstance(candidates, list) and len(candidates) > 1 and not code:
            remote_ambiguous = True

        tup = (code, qty, status)
        return ComparableRemoteResult(
            remote_result_id=chosen.id,
            status=status,
            internal_code=code,
            quantity=qty,
            ambiguous=remote_ambiguous,
            completed_at=chosen.finished_at or state.finished_at,
            pipeline_version=remote_pipeline_version,
            strategy=chosen.strategy or state.last_strategy,
            fingerprint=fingerprint_from_tuple(tup, chosen.id),
        )
