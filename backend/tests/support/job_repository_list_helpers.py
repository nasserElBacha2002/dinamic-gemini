"""Shared helpers for JobRepository test doubles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.domain.jobs.entities import Job


def list_jobs_for_targets_from_store(
    store: Mapping[str, Job],
    target_type: str,
    target_ids: Sequence[str],
    *,
    job_type: str | None = None,
) -> list[Job]:
    """Filter an in-memory job store the same way production repositories should."""
    if not target_ids:
        return []
    id_set = frozenset(dict.fromkeys(target_ids))
    return [
        job
        for job in store.values()
        if job.target_type == target_type
        and job.target_id in id_set
        and (job_type is None or job.job_type == job_type)
    ]
