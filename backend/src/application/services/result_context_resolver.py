"""
Result Context Resolver — Phase 2 multi-run reads.

Resolves which job slice (or legacy null-job slice) applies for aisle-scoped result APIs:
explicit ``job_id`` → validated ``aisles.operational_job_id`` → legacy ``job_id IS NULL`` rows.

The operational pointer is validated the same way as an explicit job: the job must
exist and target this aisle. Stale or cross-aisle pointers fail fast (no silent legacy fallback).
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

    def _assert_job_targets_aisle(self, *, job_id: str, aisle: Aisle) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_type != "aisle" or job.target_id != aisle.id:
            raise JobDoesNotBelongToAisleError(
                f"Job {job_id} does not belong to aisle {aisle.id}"
            )

    def resolve(self, *, aisle: Aisle, explicit_job_id: Optional[str]) -> ResolvedAisleResultContext:
        if explicit_job_id is not None and str(explicit_job_id).strip():
            jid = str(explicit_job_id).strip()
            self._assert_job_targets_aisle(job_id=jid, aisle=aisle)
            return ResolvedAisleResultContext(job_id_for_slice=jid, source="explicit")

        op = str(aisle.operational_job_id).strip() if aisle.operational_job_id else ""
        if op:
            self._assert_job_targets_aisle(job_id=op, aisle=aisle)
            return ResolvedAisleResultContext(job_id_for_slice=op, source="operational")

        return ResolvedAisleResultContext(job_id_for_slice=None, source="legacy")
