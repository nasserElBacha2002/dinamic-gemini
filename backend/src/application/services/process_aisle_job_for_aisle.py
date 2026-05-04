"""
Load a v3 ``process_aisle`` job and ensure it targets the given aisle.

Shared by inventory-scoped command use cases that map missing or mis-scoped jobs
to ``AisleNotFoundError`` (HTTP 404) at the API layer.
"""

from __future__ import annotations

from src.application.errors import AisleNotFoundError
from src.application.ports.repositories import JobRepository
from src.domain.jobs.entities import Job


def require_process_aisle_job_for_aisle(
    job_repo: JobRepository,
    *,
    job_id: str,
    aisle_id: str,
) -> Job:
    """Return the job row or raise the same errors as the previous inline checks."""
    job = job_repo.get_by_id(job_id)
    if job is None:
        raise AisleNotFoundError(f"Job {job_id} not found for aisle {aisle_id}")
    if job.target_type != "aisle" or job.target_id != aisle_id:
        raise AisleNotFoundError(f"Job {job_id} does not belong to aisle {aisle_id}")
    if job.job_type != "process_aisle":
        raise ValueError(f"Job {job_id} is not a process_aisle job")
    return job
