"""
Result Context Resolver — Phase 2 multi-run reads.

Resolves which job slice (or legacy null-job slice) applies for aisle-scoped result APIs:
explicit ``job_id`` → ``aisles.operational_job_id`` → legacy ``job_id IS NULL`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from src.application.errors import JobDoesNotBelongToAisleError, JobNotFoundError
from src.application.ports.repositories import JobRepository
from src.domain.aisle.entities import Aisle

ResultContextSource = Literal["explicit", "operational", "legacy"]


@dataclass(frozen=True)
class ResolvedAisleResultContext:
    """Effective job id for repository filters: ``None`` means legacy ``job_id IS NULL`` slice."""

    job_id_for_slice: Optional[str]
    source: ResultContextSource


class ResultContextResolver:
    """Central resolver for job-scoped aisle reads (application layer, HTTP-agnostic)."""

    def __init__(self, job_repo: JobRepository) -> None:
        self._job_repo = job_repo

    def resolve(self, *, aisle: Aisle, explicit_job_id: Optional[str]) -> ResolvedAisleResultContext:
        if explicit_job_id is not None and str(explicit_job_id).strip():
            jid = str(explicit_job_id).strip()
            job = self._job_repo.get_by_id(jid)
            if job is None:
                raise JobNotFoundError(f"Job not found: {jid}")
            if job.target_type != "aisle" or job.target_id != aisle.id:
                raise JobDoesNotBelongToAisleError(
                    f"Job {jid} does not belong to aisle {aisle.id}"
                )
            return ResolvedAisleResultContext(job_id_for_slice=jid, source="explicit")

        if aisle.operational_job_id:
            return ResolvedAisleResultContext(
                job_id_for_slice=aisle.operational_job_id, source="operational"
            )

        return ResolvedAisleResultContext(job_id_for_slice=None, source="legacy")
