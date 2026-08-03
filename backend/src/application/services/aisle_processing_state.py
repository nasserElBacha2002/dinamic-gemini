"""Aisle processing-state read model (shared mobile/web recovery contract)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.domain.jobs.entities import Job, JobStatus

_ACTIVE = {
    JobStatus.QUEUED,
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
}
_TERMINAL_OK = {JobStatus.SUCCEEDED}
_TERMINAL_FAIL = {JobStatus.FAILED, JobStatus.CANCELED, JobStatus.TIMED_OUT}


@dataclass(frozen=True)
class AisleProcessingStateView:
    state: str
    job_id: str | None
    job_status: str | None
    idempotency_key: str | None
    recoverable: bool
    can_start_new: bool
    updated_at: datetime | None
    failure_code: str | None


def _idempotency_from_job(job: Job) -> str | None:
    payload = job.payload_json if isinstance(job.payload_json, dict) else {}
    key = payload.get("idempotency_key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def _failure_code(job: Job) -> str | None:
    if job.failure_code:
        return job.failure_code
    if job.finalization_error_code:
        return job.finalization_error_code
    return None


def resolve_aisle_processing_state(
    *,
    latest_job: Job | None,
    recent_jobs: tuple[Job, ...] | list[Job],
    operational_job_id: str | None,
    stale_after_seconds: int = 900,
) -> AisleProcessingStateView:
    """Map aisle jobs to a shared mobile/web processing-state contract."""
    candidates: list[Job] = []
    if latest_job is not None:
        candidates.append(latest_job)
    for job in recent_jobs:
        if latest_job is None or job.id != latest_job.id:
            candidates.append(job)

    active = next((j for j in candidates if j.status in _ACTIVE), None)
    if active is not None:
        started = active.started_at or active.created_at
        if started is not None and active.status in {JobStatus.QUEUED, JobStatus.STARTING}:
            now = datetime.now(timezone.utc)
            started_aware = started if started.tzinfo else started.replace(tzinfo=timezone.utc)
            age_s = (now - started_aware).total_seconds()
            if age_s > stale_after_seconds:
                return AisleProcessingStateView(
                    state="RECOVERY_REQUIRED",
                    job_id=active.id,
                    job_status=active.status.value,
                    idempotency_key=_idempotency_from_job(active),
                    recoverable=True,
                    can_start_new=False,
                    updated_at=active.updated_at,
                    failure_code="STALE_STARTING_OR_QUEUED",
                )
        return AisleProcessingStateView(
            state="RUNNING" if active.status is JobStatus.RUNNING else "STARTING",
            job_id=active.id,
            job_status=active.status.value,
            idempotency_key=_idempotency_from_job(active),
            recoverable=False,
            can_start_new=False,
            updated_at=active.updated_at,
            failure_code=None,
        )

    # Prefer operational pointer when terminal.
    terminal: Job | None = None
    if operational_job_id:
        terminal = next((j for j in candidates if j.id == operational_job_id), None)
    if terminal is None and candidates:
        terminal = candidates[0]

    if terminal is None:
        return AisleProcessingStateView(
            state="IDLE",
            job_id=None,
            job_status=None,
            idempotency_key=None,
            recoverable=False,
            can_start_new=True,
            updated_at=None,
            failure_code=None,
        )

    if terminal.status in _TERMINAL_OK:
        return AisleProcessingStateView(
            state="COMPLETED",
            job_id=terminal.id,
            job_status=terminal.status.value,
            idempotency_key=_idempotency_from_job(terminal),
            recoverable=False,
            can_start_new=True,
            updated_at=terminal.updated_at,
            failure_code=None,
        )

    if terminal.status in _TERMINAL_FAIL:
        return AisleProcessingStateView(
            state="FAILED",
            job_id=terminal.id,
            job_status=terminal.status.value,
            idempotency_key=_idempotency_from_job(terminal),
            recoverable=False,
            can_start_new=True,
            updated_at=terminal.updated_at,
            failure_code=_failure_code(terminal),
        )

    return AisleProcessingStateView(
        state="STALE",
        job_id=terminal.id,
        job_status=terminal.status.value,
        idempotency_key=_idempotency_from_job(terminal),
        recoverable=True,
        can_start_new=False,
        updated_at=terminal.updated_at,
        failure_code="UNKNOWN_JOB_STATE",
    )


def aisle_processing_state_to_dict(view: AisleProcessingStateView) -> dict[str, Any]:
    return {
        "state": view.state,
        "job_id": view.job_id,
        "job_status": view.job_status,
        "idempotency_key": view.idempotency_key,
        "recoverable": view.recoverable,
        "can_start_new": view.can_start_new,
        "updated_at": view.updated_at.isoformat() if view.updated_at else None,
        "failure_code": view.failure_code,
    }
