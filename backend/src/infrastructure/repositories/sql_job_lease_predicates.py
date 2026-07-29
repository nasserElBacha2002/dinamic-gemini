"""Shared SQL fragments for active job-lease fencing (Phase 6).

Keep CAS predicates identical across UoW fence SELECT and lease-gated UPDATEs.
"""

from __future__ import annotations

from datetime import datetime

from src.domain.jobs.entities import JobStatus
from src.domain.jobs.lease import JobLease

# Predicate body only (caller supplies leading WHERE id = ?).
LEASE_ACTIVE_PREDICATE_SQL = """
                  AND status IN (?, ?)
                  AND claim_owner_id = ?
                  AND lease_fencing_token = ?
                  AND lease_expires_at >= ?
"""


def lease_active_bind_params(lease: JobLease, *, now_utc: datetime) -> tuple:
    """Positional params matching ``LEASE_ACTIVE_PREDICATE_SQL`` (no job id)."""
    return (
        JobStatus.RUNNING.value,
        JobStatus.CANCEL_REQUESTED.value,
        lease.owner_id,
        lease.fencing_token,
        now_utc,
    )
