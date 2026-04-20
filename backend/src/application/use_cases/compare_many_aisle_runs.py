"""Phase 1 — baseline-centric compare-many for 2-3 explicit aisle runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.errors import (
    BenchmarkCompareManyInvalidSelectionError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository, PositionRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.inventory_processing_mode import require_test_inventory_for_experimental_features
from src.application.use_cases.benchmark_compare_support import (
    aggregate_metrics,
    compute_compare_diff,
    job_metadata_dict,
    load_consolidated_for_job_slice,
    signatures_for_consolidated,
)
from src.domain.jobs.entities import Job
from src.domain.positions.entities import Position

_MIN_JOBS = 2
_MAX_JOBS = 3


@dataclass(frozen=True)
class CompareManyAisleRunsCommand:
    inventory_id: str
    aisle_id: str
    job_ids: list[str]
    baseline_job_id: str


@dataclass(frozen=True)
class _RunData:
    job: Job
    raw_count: int
    raw_load_hit_cap: bool
    signatures: dict[str, Any]
    metrics: Any


class CompareManyAisleRunsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        position_repo: PositionRepository,
        *,
        positions_aisle_raw_cap: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._position_repo = position_repo
        self._raw_cap = max(1, int(positions_aisle_raw_cap))

    def _normalize_and_validate_selection(self, command: CompareManyAisleRunsCommand) -> tuple[list[str], str]:
        job_ids = [str(job_id).strip() for job_id in command.job_ids if str(job_id).strip()]
        baseline = (command.baseline_job_id or "").strip()
        if len(job_ids) < _MIN_JOBS:
            raise BenchmarkCompareManyInvalidSelectionError("At least 2 job_ids are required.")
        if len(job_ids) > _MAX_JOBS:
            raise BenchmarkCompareManyInvalidSelectionError("At most 3 job_ids are allowed in Phase 1.")
        if len(set(job_ids)) != len(job_ids):
            raise BenchmarkCompareManyInvalidSelectionError("job_ids must be unique.")
        if not baseline:
            raise BenchmarkCompareManyInvalidSelectionError("baseline_job_id is required.")
        if baseline not in job_ids:
            raise BenchmarkCompareManyInvalidSelectionError("baseline_job_id must be one of job_ids.")
        return job_ids, baseline

    def _validate_job(self, job_id: str, aisle_id: str) -> Job:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_type != "aisle" or job.target_id != aisle_id:
            raise JobDoesNotBelongToAisleError(f"Job {job_id} is not scoped to aisle {aisle_id}")
        return job

    def _fetch_raw(self, aisle_id: str, job_id: str) -> tuple[list[Position], bool]:
        q = PositionListQuery(
            page=1,
            page_size=self._raw_cap,
            sort_by="created_at",
            sort_dir="asc",
            job_id=job_id,
        )
        rows = list(self._position_repo.list_by_aisle_query(aisle_id, q))
        return rows, len(rows) >= self._raw_cap

    def execute(self, command: CompareManyAisleRunsCommand) -> dict[str, Any]:
        job_ids, baseline_job_id = self._normalize_and_validate_selection(command)
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        require_test_inventory_for_experimental_features(inv)
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="merged",
        )

        run_data: dict[str, _RunData] = {}
        for job_id in job_ids:
            job = self._validate_job(job_id, command.aisle_id)
            raw_rows, cap_hit = self._fetch_raw(command.aisle_id, job_id)
            consolidated = load_consolidated_for_job_slice(positions=raw_rows)
            run_data[job_id] = _RunData(
                job=job,
                raw_count=len(raw_rows),
                raw_load_hit_cap=cap_hit,
                signatures=signatures_for_consolidated(consolidated),
                metrics=aggregate_metrics(consolidated, raw_fetched=len(raw_rows)),
            )

        baseline = run_data[baseline_job_id]
        comparisons = []
        for job_id in job_ids:
            if job_id == baseline_job_id:
                continue
            target = run_data[job_id]
            diff = compute_compare_diff(baseline.signatures, target.signatures)
            comparisons.append(
                {
                    "baseline_job_id": baseline_job_id,
                    "target_job_id": job_id,
                    "diff_summary": {
                        "keys_only_in_a": diff.keys_only_in_a,
                        "keys_only_in_b": diff.keys_only_in_b,
                        "keys_in_both": diff.keys_in_both,
                        "quantity_changed": diff.quantity_changed,
                        "sku_changed": diff.sku_changed,
                        "position_code_changed": diff.position_code_changed,
                    },
                }
            )

        jobs_payload = []
        raw_flags = []
        for job_id in job_ids:
            run = run_data[job_id]
            jobs_payload.append(
                {
                    **job_metadata_dict(run.job),
                    "metrics": {
                        "raw_rows_considered": run.metrics.raw_rows_considered,
                        "consolidated_positions": run.metrics.consolidated_positions,
                        "total_quantity": run.metrics.total_quantity,
                        "unknown_internal_code_count": run.metrics.unknown_internal_code_count,
                        "needs_review_count": run.metrics.needs_review_count,
                    },
                }
            )
            raw_flags.append({"job_id": job_id, "truncated": run.raw_load_hit_cap})

        return {
            "inventory_id": command.inventory_id,
            "aisle_id": command.aisle_id,
            "workflow": "benchmark_compare_many",
            "read_only": True,
            "baseline_job_id": baseline_job_id,
            "jobs": jobs_payload,
            "comparisons": comparisons,
            "raw_fetch_truncated": raw_flags,
        }
