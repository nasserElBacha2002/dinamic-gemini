"""Single source of truth for billable aisle-job cost aggregation.

Merchandise counts remain on the operational / current result slice elsewhere.
Cost totals here are independent: sum every countable ``process_aisle`` job
(by unique job id), never ``SUM(DISTINCT cost)`` and never join-inflate via items.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from src.application.ports.repositories import JobRepository
from src.application.services.analytics_cost_snapshot_parser import (
    ParsedCostSnapshot,
    parse_llm_cost_snapshot,
)
from src.domain.jobs.entities import Job, JobStatus

logger = logging.getLogger(__name__)

PROCESS_AISLE_JOB_TYPE = "process_aisle"
AISLE_TARGET_TYPE = "aisle"

# Max target_ids per SQL ``IN`` clause (parameter-limit safety only — never caps jobs/runs).
TARGET_ID_BATCH_SIZE = 500

# Finalized statuses that may carry billable LLM usage (aligned with cancel/terminal domain).
#
# Status policy (explicit):
# - SUCCEEDED: include when snapshot aggregatable — production success path.
# - FAILED: include when snapshot aggregatable — billed usage before failure.
# - CANCELED: include when snapshot aggregatable — cooperative cancel after work.
# - TIMED_OUT: include when snapshot aggregatable — domain-terminal (reserved; rare).
# - QUEUED / STARTING / RUNNING / CANCEL_REQUESTED: never include (not finalized).
BILLABLE_TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELED,
        JobStatus.TIMED_OUT,
    }
)

# Capture statuses whose ``computed_cost.total_cost`` is included in money totals.
AGGREGATABLE_CAPTURE_STATUSES: frozenset[str] = frozenset({"exact", "estimated", "partial"})


def aggregatable_cost_amount(parsed: ParsedCostSnapshot) -> Decimal | None:
    """Return monetary amount when capture status and total_cost are aggregatable.

    Zero is a known cost (not missing). Negatives are rejected by the snapshot parser.
    """
    if parsed.capture_status not in AGGREGATABLE_CAPTURE_STATUSES:
        return None
    return parsed.cost_amount


def billable_cost_for_job(job: Job) -> Decimal | None:
    """Cost of one job if it is a countable process_aisle execution; else None.

    Inclusion:
    - ``job_type == process_aisle`` and ``target_type == aisle``
    - status in :data:`BILLABLE_TERMINAL_STATUSES`
    - persisted ``llm_cost_snapshot`` with aggregatable capture_status
    - valid non-negative ``computed_cost.total_cost`` (including zero)

    Exclusion:
    - non-terminal statuses (queued / starting / running / cancel_requested)
    - missing / unavailable snapshot or missing / invalid total_cost
    - non–process_aisle or non-aisle targets
    """
    if job.job_type != PROCESS_AISLE_JOB_TYPE or job.target_type != AISLE_TARGET_TYPE:
        return None
    if job.status not in BILLABLE_TERMINAL_STATUSES:
        return None
    result_json = job.result_json if isinstance(job.result_json, dict) else None
    return aggregatable_cost_amount(parse_llm_cost_snapshot(result_json))


def _unique_jobs_by_id(jobs: Sequence[Job]) -> dict[str, Job]:
    """Dedupe by job id; keep first occurrence; warn on conflicting payloads."""
    unique: dict[str, Job] = {}
    for job in jobs:
        existing = unique.get(job.id)
        if existing is None:
            unique[job.id] = job
        elif existing != job:
            logger.warning(
                "Conflicting duplicate job returned while aggregating aisle costs",
                extra={"job_id": job.id},
            )
    return unique


def sum_billable_costs_by_aisle_id(jobs: Sequence[Job]) -> dict[str, Decimal]:
    """Sum billable costs per aisle; dedupe by job id before summing (not by cost value)."""
    unique = _unique_jobs_by_id(jobs)

    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    has_cost: set[str] = set()
    for job in unique.values():
        amount = billable_cost_for_job(job)
        if amount is None:
            continue
        aisle_id = str(job.target_id).strip()
        if not aisle_id:
            continue
        totals[aisle_id] += amount
        has_cost.add(aisle_id)
    return {aisle_id: totals[aisle_id] for aisle_id in has_cost}


def format_cost_decimal(amount: Decimal | None) -> str:
    """Export / display string; empty when no aggregatable cost."""
    if amount is None:
        return ""
    text = f"{amount:.8f}".rstrip("0").rstrip(".")
    return text


def load_billable_costs_by_aisle_id(
    job_repo: JobRepository,
    aisle_ids: Sequence[str],
) -> dict[str, Decimal]:
    """Batch-load process_aisle jobs for aisles and return per-aisle billable cost sums."""
    if not aisle_ids:
        return {}
    jobs = job_repo.list_jobs_for_targets(
        AISLE_TARGET_TYPE,
        list(aisle_ids),
        job_type=PROCESS_AISLE_JOB_TYPE,
    )
    return sum_billable_costs_by_aisle_id(jobs)


def export_cost_strings_by_aisle_id(
    job_repo: JobRepository | None,
    aisle_ids: Sequence[str],
) -> dict[str, str]:
    """Map each aisle id to export cost string (accumulated); missing → empty string."""
    if job_repo is None or not aisle_ids:
        return {aid: "" for aid in aisle_ids}
    sums = load_billable_costs_by_aisle_id(job_repo, aisle_ids)
    return {aid: format_cost_decimal(sums.get(aid)) for aid in aisle_ids}


def export_inventory_total_cost_string(
    job_repo: JobRepository | None,
    aisle_ids: Sequence[str],
) -> str:
    """Sum of billable costs across all given aisles (unique jobs); empty if none."""
    if job_repo is None or not aisle_ids:
        return ""
    sums = load_billable_costs_by_aisle_id(job_repo, aisle_ids)
    if not sums:
        return ""
    total = sum(sums.values(), Decimal("0"))
    return format_cost_decimal(total)
