"""
Result Context Resolver — Phase 2 multi-run reads.

Resolves which job slice (or legacy null-job slice) applies for aisle-scoped result APIs:
explicit ``job_id`` → validated ``aisles.operational_job_id`` → legacy ``job_id IS NULL`` rows.

**Transitional default (Phase 2):** when operational is unset and the legacy slice is empty but
job-scoped rows exist, fall back to the **latest succeeded** ``process_aisle`` job for that aisle
(so default reads match a real dataset without requiring ``operational_job_id`` or an explicit
``job_id`` query param). Mixed legacy + job-scoped aisles still prefer the legacy slice when it
is non-empty.

The operational pointer is validated the same way as an explicit job: the job must
exist and target this aisle. Stale or cross-aisle pointers fail fast (no silent legacy fallback).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from src.application.errors import JobDoesNotBelongToAisleError, JobNotFoundError
from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import JobRepository, PositionRepository
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import JobStatus

ResultContextSource = Literal["explicit", "operational", "legacy", "latest_succeeded"]


@dataclass(frozen=True)
class ResolvedAisleResultContext:
    """Effective job id for repository filters: ``None`` means legacy ``job_id IS NULL`` slice."""

    job_id_for_slice: Optional[str]
    source: ResultContextSource


class ResultContextResolver:
    """Central resolver for job-scoped aisle reads (application layer, HTTP-agnostic)."""

    def __init__(
        self,
        job_repo: JobRepository,
        position_repo: Optional[PositionRepository] = None,
    ) -> None:
        self._job_repo = job_repo
        self._position_repo = position_repo

    def _assert_job_targets_aisle(self, *, job_id: str, aisle: Aisle) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_type != "aisle" or job.target_id != aisle.id:
            raise JobDoesNotBelongToAisleError(
                f"Job {job_id} does not belong to aisle {aisle.id}"
            )

    def _legacy_slice_non_empty(self, aisle_id: str) -> bool:
        if self._position_repo is None:
            return False
        q = PositionListQuery(
            page=1,
            page_size=1,
            sort_by="created_at",
            sort_dir="asc",
            job_id=None,
        )
        rows = self._position_repo.list_by_aisle_query(aisle_id, q)
        return len(rows) > 0

    def _latest_succeeded_process_aisle_job_id(self, aisle_id: str) -> Optional[str]:
        jobs = self._job_repo.list_jobs_for_target("aisle", aisle_id, limit=100)
        for j in jobs:
            if j.job_type == "process_aisle" and j.status == JobStatus.SUCCEEDED:
                return j.id
        return None

    def resolve(self, *, aisle: Aisle, explicit_job_id: Optional[str]) -> ResolvedAisleResultContext:
        if explicit_job_id is not None and str(explicit_job_id).strip():
            jid = str(explicit_job_id).strip()
            self._assert_job_targets_aisle(job_id=jid, aisle=aisle)
            return ResolvedAisleResultContext(job_id_for_slice=jid, source="explicit")

        op = str(aisle.operational_job_id).strip() if aisle.operational_job_id else ""
        if op:
            self._assert_job_targets_aisle(job_id=op, aisle=aisle)
            return ResolvedAisleResultContext(job_id_for_slice=op, source="operational")

        if self._position_repo is not None and not self._legacy_slice_non_empty(aisle.id):
            sj = self._latest_succeeded_process_aisle_job_id(aisle.id)
            if sj:
                self._assert_job_targets_aisle(job_id=sj, aisle=aisle)
                return ResolvedAisleResultContext(job_id_for_slice=sj, source="latest_succeeded")

        return ResolvedAisleResultContext(job_id_for_slice=None, source="legacy")
