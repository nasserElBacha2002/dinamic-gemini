"""Phase 5 — operational job/aisle consistency diagnostics (read-only by default)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job, JobStatus


class ConsistencyFindingKind(str, Enum):
    RUNNING_WITHOUT_LEASE = "RUNNING_WITHOUT_LEASE"
    RUNNING_LEASE_EXPIRED = "RUNNING_LEASE_EXPIRED"
    SUCCEEDED_WITHOUT_FINISHED_AT = "SUCCEEDED_WITHOUT_FINISHED_AT"
    FAILED_WITHOUT_FAILURE_CODE = "FAILED_WITHOUT_FAILURE_CODE"
    TERMINAL_JOB_AISLE_PROCESSING = "TERMINAL_JOB_AISLE_PROCESSING"
    RUNNING_JOB_AISLE_TERMINAL = "RUNNING_JOB_AISLE_TERMINAL"
    OPERATIONAL_JOB_NOT_SUCCEEDED = "OPERATIONAL_JOB_NOT_SUCCEEDED"
    FINALIZATION_STUCK = "FINALIZATION_STUCK"


class ConsistencyAction(str, Enum):
    DIAGNOSE = "diagnose"
    ALERT = "alert"
    AUTO_RECOVERY = "auto_recovery"
    MANUAL_RECOVERY = "manual_recovery"


@dataclass(frozen=True, slots=True)
class ConsistencyFinding:
    kind: ConsistencyFindingKind
    action: ConsistencyAction
    job_id: str | None
    aisle_id: str | None
    detail: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _status_value(status: object) -> str:
    raw = getattr(status, "value", status)
    return str(raw).strip().lower() if raw is not None else ""


def audit_job_row(
    job: Job | None,
    *,
    aisle: Aisle | None = None,
    now: datetime | None = None,
    finalization_stuck_after_sec: int = 3600,
) -> list[ConsistencyFinding]:
    """Inspect a single job (+ optional aisle) for operational inconsistencies."""
    if job is None:
        return []
    now = now or _utc_now()
    findings: list[ConsistencyFinding] = []
    status_value = _status_value(job.status)
    job_id = job.id
    aisle_id = job.target_id if job.target_type == "aisle" else None

    lease_owner = job.claim_owner_id
    lease_expires = job.lease_expires_at

    active_statuses = frozenset(
        {
            JobStatus.RUNNING.value,
            JobStatus.STARTING.value,
            JobStatus.CANCEL_REQUESTED.value,
        }
    )
    terminal_statuses = frozenset(
        {
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELED.value,
        }
    )

    if status_value in active_statuses:
        if not lease_owner and lease_expires is None:
            findings.append(
                ConsistencyFinding(
                    ConsistencyFindingKind.RUNNING_WITHOUT_LEASE,
                    ConsistencyAction.ALERT,
                    job_id,
                    aisle_id,
                    "Active job has no lease owner/expiry",
                )
            )
        elif lease_expires is not None and lease_expires < now:
            findings.append(
                ConsistencyFinding(
                    ConsistencyFindingKind.RUNNING_LEASE_EXPIRED,
                    ConsistencyAction.AUTO_RECOVERY,
                    job_id,
                    aisle_id,
                    "Active job lease expired (stale-fail candidate)",
                )
            )

    if status_value == JobStatus.SUCCEEDED.value and job.finished_at is None:
        findings.append(
            ConsistencyFinding(
                ConsistencyFindingKind.SUCCEEDED_WITHOUT_FINISHED_AT,
                ConsistencyAction.DIAGNOSE,
                job_id,
                aisle_id,
                "SUCCEEDED missing finished_at",
            )
        )

    if status_value == JobStatus.FAILED.value and not job.failure_code:
        findings.append(
            ConsistencyFinding(
                ConsistencyFindingKind.FAILED_WITHOUT_FAILURE_CODE,
                ConsistencyAction.DIAGNOSE,
                job_id,
                aisle_id,
                "FAILED missing failure_code",
            )
        )

    fin_value = _status_value(job.finalization_status)
    updated = job.updated_at
    if (
        fin_value == "in_progress"
        and status_value in terminal_statuses
        and updated is not None
        and (now - updated).total_seconds() > finalization_stuck_after_sec
    ):
        findings.append(
            ConsistencyFinding(
                ConsistencyFindingKind.FINALIZATION_STUCK,
                ConsistencyAction.MANUAL_RECOVERY,
                job_id,
                aisle_id,
                "Finalization IN_PROGRESS on terminal job beyond threshold",
            )
        )

    if aisle is not None:
        aisle_status_value = _status_value(aisle.status)
        aisle_id = aisle.id or aisle_id
        if status_value in terminal_statuses and aisle_status_value in {
            "processing",
            "queued",
        }:
            findings.append(
                ConsistencyFinding(
                    ConsistencyFindingKind.TERMINAL_JOB_AISLE_PROCESSING,
                    ConsistencyAction.MANUAL_RECOVERY,
                    job_id,
                    aisle_id,
                    "Terminal job with aisle still active",
                )
            )
        if status_value in {
            JobStatus.RUNNING.value,
            JobStatus.STARTING.value,
        } and aisle_status_value in {
            "completed",
            "failed",
            "canceled",
        }:
            findings.append(
                ConsistencyFinding(
                    ConsistencyFindingKind.RUNNING_JOB_AISLE_TERMINAL,
                    ConsistencyAction.ALERT,
                    job_id,
                    aisle_id,
                    "Running job with terminal aisle",
                )
            )
        op_job = aisle.operational_job_id
        if op_job and op_job == job_id and status_value != JobStatus.SUCCEEDED.value:
            findings.append(
                ConsistencyFinding(
                    ConsistencyFindingKind.OPERATIONAL_JOB_NOT_SUCCEEDED,
                    ConsistencyAction.ALERT,
                    job_id,
                    aisle_id,
                    "operational_job_id points at non-SUCCEEDED job",
                )
            )

    return findings


def audit_jobs(
    jobs: Iterable[Job],
    *,
    aisle_by_id: dict[str, Aisle] | None = None,
    now: datetime | None = None,
) -> list[ConsistencyFinding]:
    aisle_by_id = aisle_by_id or {}
    out: list[ConsistencyFinding] = []
    for job in jobs:
        aisle = None
        if job.target_type == "aisle" and isinstance(job.target_id, str) and job.target_id:
            aisle = aisle_by_id.get(job.target_id)
        out.extend(audit_job_row(job, aisle=aisle, now=now))
    return out
