"""Build the linear retry chain for an aisle job (retry_of_job_id links)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.application.ports.repositories import JobRepository
from src.domain.jobs.entities import Job


class RetryChainIntegrity(str, Enum):
    VALID = "VALID"
    FORKED = "FORKED"
    CYCLIC = "CYCLIC"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class RetryChainAttemptView:
    job_id: str
    attempt_number: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    failure_code: str | None
    failure_message: str | None
    execution_id: str | None
    provider_name: str | None
    model_name: str | None
    is_selected: bool
    is_current: bool
    is_successful: bool


@dataclass(frozen=True)
class RetryChainView:
    root_job_id: str
    selected_job_id: str
    current_job_id: str
    integrity: RetryChainIntegrity
    attempts: list[RetryChainAttemptView]
    warnings: list[str]


class JobRetryChainService:
    """Walk ``retry_of_job_id`` forward/back within one aisle target."""

    def __init__(self, job_repo: JobRepository) -> None:
        self._job_repo = job_repo

    def build(self, selected: Job, *, aisle_id: str) -> RetryChainView:
        if selected.target_type != "aisle" or selected.target_id != aisle_id:
            raise ValueError("selected job is not scoped to aisle")

        siblings = list(self._job_repo.list_jobs_for_target("aisle", aisle_id, limit=500))
        by_id = {j.id: j for j in siblings if j.job_type == selected.job_type}
        if selected.id not in by_id:
            by_id[selected.id] = selected

        warnings: list[str] = []
        integrity = RetryChainIntegrity.VALID

        root, root_warnings, root_integrity = self._find_root(selected, by_id)
        warnings.extend(root_warnings)
        if root_integrity != RetryChainIntegrity.VALID:
            integrity = root_integrity

        ordered, walk_warnings, walk_integrity = self._walk_forward(root, by_id)
        warnings.extend(walk_warnings)
        if walk_integrity != RetryChainIntegrity.VALID and integrity == RetryChainIntegrity.VALID:
            integrity = walk_integrity
        if not ordered:
            ordered = [selected]

        seen: set[str] = set()
        deduped: list[Job] = []
        for job in ordered:
            if job.id in seen:
                integrity = RetryChainIntegrity.CYCLIC
                warnings.append(f"cycle_detected_at={job.id}")
                break
            seen.add(job.id)
            deduped.append(job)

        current = deduped[-1]
        for job in reversed(deduped):
            if job.status.value == "succeeded":
                current = job
                break

        attempts: list[RetryChainAttemptView] = []
        for index, job in enumerate(deduped, start=1):
            attempts.append(
                RetryChainAttemptView(
                    job_id=job.id,
                    attempt_number=int(job.attempt_count or index),
                    status=job.status.value,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                    failure_code=job.failure_code,
                    failure_message=job.failure_message,
                    execution_id=job.execution_id,
                    provider_name=job.provider_name,
                    model_name=job.model_name,
                    is_selected=job.id == selected.id,
                    is_current=job.id == current.id,
                    is_successful=job.status.value == "succeeded",
                )
            )

        return RetryChainView(
            root_job_id=root.id,
            selected_job_id=selected.id,
            current_job_id=current.id,
            integrity=integrity,
            attempts=attempts,
            warnings=warnings,
        )

    def _find_root(
        self, job: Job, by_id: dict[str, Job]
    ) -> tuple[Job, list[str], RetryChainIntegrity]:
        current = job
        visited: set[str] = set()
        warnings: list[str] = []
        integrity = RetryChainIntegrity.VALID
        while current.retry_of_job_id:
            if current.id in visited:
                return current, warnings + ["cycle_while_finding_root"], RetryChainIntegrity.CYCLIC
            visited.add(current.id)
            parent = by_id.get(current.retry_of_job_id)
            if parent is None:
                parent = self._job_repo.get_by_id(current.retry_of_job_id)
            if parent is None:
                warnings.append(f"missing_parent={current.retry_of_job_id}")
                return current, warnings, RetryChainIntegrity.INCOMPLETE
            if parent.target_type != "aisle" or parent.target_id != job.target_id:
                warnings.append(f"parent_wrong_target={parent.id}")
                return current, warnings, RetryChainIntegrity.INCOMPLETE
            if parent.job_type != job.job_type:
                warnings.append(f"parent_wrong_job_type={parent.id}")
                return current, warnings, RetryChainIntegrity.INCOMPLETE
            current = parent
        return current, warnings, integrity

    def _walk_forward(
        self, root: Job, by_id: dict[str, Job]
    ) -> tuple[list[Job], list[str], RetryChainIntegrity]:
        children: dict[str, list[Job]] = {}
        for job in by_id.values():
            parent = (job.retry_of_job_id or "").strip()
            if not parent:
                continue
            children.setdefault(parent, []).append(job)
        for kids in children.values():
            kids.sort(key=lambda j: (j.created_at, j.id))

        chain: list[Job] = [root]
        cursor = root
        warnings: list[str] = []
        integrity = RetryChainIntegrity.VALID
        guard = 0
        while guard < 100:
            guard += 1
            next_jobs = children.get(cursor.id) or []
            if not next_jobs:
                break
            if len(next_jobs) > 1:
                integrity = RetryChainIntegrity.FORKED
                warnings.append(
                    f"fork_at={cursor.id}:children={[j.id for j in next_jobs]}"
                )
                # Include all children as siblings in warnings; continue linear path
                # using earliest child only for the primary chain.
            cursor = next_jobs[0]
            if cursor.id in {j.id for j in chain}:
                return chain, warnings + [f"cycle_at={cursor.id}"], RetryChainIntegrity.CYCLIC
            chain.append(cursor)
        if guard >= 100:
            warnings.append("chain_exceeded_max_depth")
            integrity = RetryChainIntegrity.INCOMPLETE
        return chain, warnings, integrity
