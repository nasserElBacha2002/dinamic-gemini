"""Aisle processing-state read model (shared mobile/web recovery contract)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from src.domain.jobs.entities import Job, JobStatus

_ACTIVE = {
    JobStatus.QUEUED,
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
}
_TERMINAL_OK = {JobStatus.SUCCEEDED}
_TERMINAL_FAIL = {JobStatus.FAILED, JobStatus.CANCELED, JobStatus.TIMED_OUT}

WORKER_LAUNCH_FAILED = "WORKER_LAUNCH_FAILED"


class _Clock(Protocol):
    def now(self) -> datetime: ...


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


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _has_active_lease(job: Job, *, now: datetime) -> bool:
    if job.status not in (
        JobStatus.RUNNING,
        JobStatus.STARTING,
        JobStatus.CANCEL_REQUESTED,
    ):
        return False
    if not (job.claim_owner_id or "").strip():
        return False
    exp = _aware(job.lease_expires_at)
    if exp is None:
        return False
    return exp >= now


def _heartbeat_age_seconds(job: Job, *, now: datetime) -> float | None:
    reference = _aware(job.last_heartbeat_at) or _aware(job.updated_at)
    if reference is None:
        return None
    return (now - reference).total_seconds()


def _created_age_seconds(job: Job, *, now: datetime) -> float | None:
    started = _aware(job.started_at) or _aware(job.created_at)
    if started is None:
        return None
    return (now - started).total_seconds()


def _active_job_view(
    active: Job,
    *,
    state: str,
    recoverable: bool,
    can_start_new: bool,
    failure_code: str | None,
) -> AisleProcessingStateView:
    return AisleProcessingStateView(
        state=state,
        job_id=active.id,
        job_status=active.status.value,
        idempotency_key=_idempotency_from_job(active),
        recoverable=recoverable,
        can_start_new=can_start_new,
        updated_at=active.updated_at,
        failure_code=failure_code,
    )


def _classify_active_job(
    active: Job,
    *,
    now: datetime,
    stale_after_seconds: int,
) -> AisleProcessingStateView:
    """Classify an active job using lease/heartbeat evidence — not age alone."""
    # Worker launch failed while still STARTING/QUEUED → safe to recover.
    if (active.failure_code or "").strip() == WORKER_LAUNCH_FAILED:
        return _active_job_view(
            active,
            state="RECOVERY_REQUIRED",
            recoverable=True,
            can_start_new=False,
            failure_code=WORKER_LAUNCH_FAILED,
        )

    # Live lease → never mark recovery.
    if _has_active_lease(active, now=now):
        return _active_job_view(
            active,
            state="RUNNING" if active.status is JobStatus.RUNNING else "STARTING",
            recoverable=False,
            can_start_new=False,
            failure_code=None,
        )

    # RUNNING / CANCEL_REQUESTED without lease: heartbeat decides.
    if active.status in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
        hb_age = _heartbeat_age_seconds(active, now=now)
        if hb_age is not None and hb_age > stale_after_seconds:
            return _active_job_view(
                active,
                state="RECOVERY_REQUIRED",
                recoverable=True,
                can_start_new=False,
                failure_code="STALE_LEASE_OR_HEARTBEAT",
            )
        return _active_job_view(
            active,
            state="RUNNING",
            recoverable=False,
            can_start_new=False,
            failure_code=None,
        )

    # QUEUED / STARTING without lease: age → suspected; no lease + old → recovery.
    created_age = _created_age_seconds(active, now=now)
    if created_age is not None and created_age > stale_after_seconds:
        # No owner / lease → recoverable orphan. If somehow claimed without expiry,
        # keep as suspected until recover inspects further.
        if not (active.claim_owner_id or "").strip() or active.lease_expires_at is None:
            return _active_job_view(
                active,
                state="RECOVERY_REQUIRED",
                recoverable=True,
                can_start_new=False,
                failure_code="STALE_STARTING_OR_QUEUED",
            )
        return _active_job_view(
            active,
            state="SUSPECTED_STALE",
            recoverable=False,
            can_start_new=False,
            failure_code="SUSPECTED_STALE_STARTING_OR_QUEUED",
        )

    return _active_job_view(
        active,
        state="RUNNING" if active.status is JobStatus.RUNNING else "STARTING",
        recoverable=False,
        can_start_new=False,
        failure_code=None,
    )


def resolve_aisle_processing_state(
    *,
    latest_job: Job | None,
    recent_jobs: tuple[Job, ...] | list[Job],
    operational_job_id: str | None,
    stale_after_seconds: int = 900,
    clock: _Clock | None = None,
    now: datetime | None = None,
) -> AisleProcessingStateView:
    """Map aisle jobs to a shared mobile/web processing-state contract."""
    if now is None:
        now = clock.now() if clock is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    candidates: list[Job] = []
    if latest_job is not None:
        candidates.append(latest_job)
    for job in recent_jobs:
        if latest_job is None or job.id != latest_job.id:
            candidates.append(job)

    active = next((j for j in candidates if j.status in _ACTIVE), None)
    if active is not None:
        return _classify_active_job(
            active, now=now, stale_after_seconds=stale_after_seconds
        )

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
