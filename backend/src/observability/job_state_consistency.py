"""Phase 5 — operational job/aisle consistency diagnostics (read-only by default)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


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


def audit_job_row(
    job: Any,
    *,
    aisle: Any | None = None,
    now: datetime | None = None,
    finalization_stuck_after_sec: int = 3600,
) -> list[ConsistencyFinding]:
    """Inspect a single job (+ optional aisle) for operational inconsistencies."""
    now = now or _utc_now()
    findings: list[ConsistencyFinding] = []
    status = getattr(job, "status", None)
    status_value = getattr(status, "value", status)
    job_id = getattr(job, "id", None)
    aisle_id = None
    if getattr(job, "target_type", None) == "aisle":
        aisle_id = getattr(job, "target_id", None)

    lease_owner = getattr(job, "claim_owner_id", None) or getattr(job, "lease_owner_id", None)
    lease_expires = getattr(job, "lease_expires_at", None)

    if status_value in {"RUNNING", "STARTING", "CANCEL_REQUESTED"}:
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

    if status_value == "SUCCEEDED" and getattr(job, "finished_at", None) is None:
        findings.append(
            ConsistencyFinding(
                ConsistencyFindingKind.SUCCEEDED_WITHOUT_FINISHED_AT,
                ConsistencyAction.DIAGNOSE,
                job_id,
                aisle_id,
                "SUCCEEDED missing finished_at",
            )
        )

    if status_value == "FAILED" and not getattr(job, "failure_code", None):
        findings.append(
            ConsistencyFinding(
                ConsistencyFindingKind.FAILED_WITHOUT_FAILURE_CODE,
                ConsistencyAction.DIAGNOSE,
                job_id,
                aisle_id,
                "FAILED missing failure_code",
            )
        )

    fin_status = getattr(job, "finalization_status", None)
    fin_value = getattr(fin_status, "value", fin_status)
    updated = getattr(job, "updated_at", None) or getattr(job, "finalization_updated_at", None)
    if (
        fin_value in {"IN_PROGRESS", "in_progress"}
        and status_value in {"SUCCEEDED", "FAILED", "CANCELED"}
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
        aisle_status = getattr(aisle, "status", None)
        aisle_status_value = getattr(aisle_status, "value", aisle_status)
        aisle_id = getattr(aisle, "id", None) or aisle_id
        if status_value in {"SUCCEEDED", "FAILED", "CANCELED"} and aisle_status_value in {
            "PROCESSING",
            "QUEUED",
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
        if status_value in {"RUNNING", "STARTING"} and aisle_status_value in {
            "COMPLETED",
            "FAILED",
            "CANCELED",
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
        op_job = getattr(aisle, "operational_job_id", None)
        if op_job and op_job == job_id and status_value != "SUCCEEDED":
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
    jobs: Iterable[Any],
    *,
    aisle_by_id: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> list[ConsistencyFinding]:
    aisle_by_id = aisle_by_id or {}
    out: list[ConsistencyFinding] = []
    for job in jobs:
        aisle = None
        if getattr(job, "target_type", None) == "aisle":
            target_id = getattr(job, "target_id", None)
            if isinstance(target_id, str) and target_id:
                aisle = aisle_by_id.get(target_id)
        out.extend(audit_job_row(job, aisle=aisle, now=now))
    return out
