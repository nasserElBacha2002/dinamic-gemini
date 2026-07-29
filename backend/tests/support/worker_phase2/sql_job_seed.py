"""Shared SQL seed helpers for worker Phase 2 integration tests."""

from __future__ import annotations

from datetime import datetime

from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
from src.infrastructure.repositories.sql_result_evidence_repository import (
    SqlResultEvidenceRepository,
)


def seed_process_aisle_job(
    client,
    *,
    job_id: str,
    aisle_id: str,
    now: datetime,
    status: JobStatus = JobStatus.RUNNING,
    lease_fencing_token: int = 1,
) -> Job:
    """Insert ``inventory_jobs`` row required by FKs (positions / operational_job)."""
    job = Job(
        job_id,
        "aisle",
        aisle_id,
        "process_aisle",
        status,
        {},
        now,
        now,
        lease_fencing_token=lease_fencing_token,
        lease_expires_at=now,
        lease_acquired_at=now,
        claim_owner_id="sql-integration-owner",
    )
    SqlJobRepository(client).save(job)
    return job


def sql_result_evidence_repo(client) -> SqlResultEvidenceRepository:
    return SqlResultEvidenceRepository(client)
