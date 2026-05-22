"""Phase 1/2 — baseline-centric compare-many for 2-3 explicit aisle runs."""

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
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.inventory_processing_mode import (
    require_test_inventory_for_experimental_features,
)
from src.application.use_cases.shared.benchmark_compare_support import (
    aggregate_metrics,
    build_compare_diff_rows,
    compute_compare_diff,
    job_execution_duration_seconds,
    job_metadata_dict,
    load_consolidated_for_job_slice,
    signatures_for_consolidated,
)
from src.domain.jobs.entities import Job
from src.domain.positions.entities import Position

_MIN_JOBS = 2
_MAX_JOBS = 3
_DEFAULT_MAX_DIFF_ROWS = 250
# TODO(phase4-scale): evaluate raising compare-many max jobs (5+) with explicit safeguards for:
# - payload size growth
# - response readability for operators
# - diff-row amplification across baseline-target pairs
# - JSON serialization and frontend rendering costs


@dataclass(frozen=True)
class CompareManyAisleRunsCommand:
    inventory_id: str
    aisle_id: str
    job_ids: list[str]
    baseline_job_id: str
    include_diff_rows: bool = False
    max_diff_rows: int | None = None


@dataclass(frozen=True)
class _RunData:
    job: Job
    raw_count: int  # number of rows actually used in compare metrics
    raw_truncated: bool
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

    def _normalize_and_validate_selection(
        self, command: CompareManyAisleRunsCommand
    ) -> tuple[list[str], str]:
        normalized_job_ids = [str(job_id).strip() for job_id in command.job_ids]
        baseline = (command.baseline_job_id or "").strip()
        if any(not job_id for job_id in normalized_job_ids):
            raise BenchmarkCompareManyInvalidSelectionError(
                "job_ids cannot contain empty or whitespace-only values."
            )
        if len(normalized_job_ids) < _MIN_JOBS:
            raise BenchmarkCompareManyInvalidSelectionError("At least 2 job_ids are required.")
        if len(normalized_job_ids) > _MAX_JOBS:
            raise BenchmarkCompareManyInvalidSelectionError("At most 3 job_ids are allowed.")
        if len(set(normalized_job_ids)) != len(normalized_job_ids):
            raise BenchmarkCompareManyInvalidSelectionError("job_ids must be unique.")
        if not baseline:
            raise BenchmarkCompareManyInvalidSelectionError("baseline_job_id is required.")
        if baseline not in normalized_job_ids:
            raise BenchmarkCompareManyInvalidSelectionError(
                "baseline_job_id must be one of job_ids."
            )
        return normalized_job_ids, baseline

    def _validate_job(self, job_id: str, aisle_id: str) -> Job:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_type != "aisle" or job.target_id != aisle_id:
            raise JobDoesNotBelongToAisleError(f"Job {job_id} is not scoped to aisle {aisle_id}")
        # Keep parity with existing binary compare: status is not restricted to SUCCEEDED here.
        # TODO(phase2-policy): confirm product policy for non-succeeded jobs and tighten if required.
        return job

    def _fetch_raw(self, aisle_id: str, job_id: str) -> tuple[list[Position], bool]:
        # Fetch one extra row so truncation is truthful, not inferred.
        q = PositionListQuery(
            page=1,
            page_size=self._raw_cap + 1,
            sort_by="created_at",
            sort_dir="asc",
            job_id=job_id,
        )
        rows = list(self._position_repo.list_by_aisle_query(aisle_id, q))
        if len(rows) > self._raw_cap:
            return rows[: self._raw_cap], True
        return rows, False

    def _effective_diff_row_cap(self, requested: int | None) -> int:
        if requested is None:
            return _DEFAULT_MAX_DIFF_ROWS
        value = int(requested)
        if value < 1:
            raise BenchmarkCompareManyInvalidSelectionError("max_diff_rows must be >= 1.")
        if value > _DEFAULT_MAX_DIFF_ROWS:
            raise BenchmarkCompareManyInvalidSelectionError(
                f"max_diff_rows must be <= {_DEFAULT_MAX_DIFF_ROWS}."
            )
        return value

    def _resolve_baseline(self, job_ids: list[str], baseline_job_id: str) -> tuple[str, list[str]]:
        if baseline_job_id not in job_ids:
            raise BenchmarkCompareManyInvalidSelectionError(
                "baseline_job_id must be one of job_ids."
            )
        targets = [job_id for job_id in job_ids if job_id != baseline_job_id]
        return baseline_job_id, targets

    @staticmethod
    def _build_delta(
        baseline_job: Job,
        target_job: Job,
        baseline_metrics: Any,
        target_metrics: Any,
    ) -> dict[str, Any]:
        b_dur = job_execution_duration_seconds(baseline_job)
        t_dur = job_execution_duration_seconds(target_job)
        return {
            "total_quantity_diff": target_metrics.total_quantity - baseline_metrics.total_quantity,
            "consolidated_positions_diff": (
                target_metrics.consolidated_positions - baseline_metrics.consolidated_positions
            ),
            "unknown_internal_code_diff": (
                target_metrics.unknown_internal_code_count
                - baseline_metrics.unknown_internal_code_count
            ),
            "needs_review_diff": target_metrics.needs_review_count
            - baseline_metrics.needs_review_count,
            "execution_time_delta": (
                None if b_dur is None or t_dur is None else float(t_dur - b_dur)
            ),
        }

    def execute(self, command: CompareManyAisleRunsCommand) -> dict[str, Any]:
        job_ids, baseline_job_id = self._normalize_and_validate_selection(command)
        diff_row_cap = (
            self._effective_diff_row_cap(command.max_diff_rows)
            if command.include_diff_rows
            else None
        )
        baseline_job_id, target_job_ids = self._resolve_baseline(job_ids, baseline_job_id)
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
            raw_rows, raw_truncated = self._fetch_raw(command.aisle_id, job_id)
            consolidated = load_consolidated_for_job_slice(positions=raw_rows)
            run_data[job_id] = _RunData(
                job=job,
                raw_count=len(raw_rows),
                raw_truncated=raw_truncated,
                signatures=signatures_for_consolidated(consolidated),
                metrics=aggregate_metrics(consolidated, raw_fetched=len(raw_rows)),
            )

        baseline = run_data[baseline_job_id]
        comparisons = []
        for job_id in target_job_ids:
            target = run_data[job_id]
            diff = compute_compare_diff(baseline.signatures, target.signatures)
            comp_payload: dict[str, Any] = {
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
                "delta": self._build_delta(
                    baseline.job,
                    target.job,
                    baseline.metrics,
                    target.metrics,
                ),
                "diff_rows": [],
                "diff_rows_truncated": False,
            }
            if command.include_diff_rows:
                assert diff_row_cap is not None
                rows, rows_truncated = build_compare_diff_rows(
                    baseline.signatures,
                    target.signatures,
                    max_rows=diff_row_cap,
                )
                comp_payload["diff_rows"] = [
                    {
                        "match_key": r.match_key,
                        "side": r.side,
                        "quantity_a": r.quantity_a,
                        "quantity_b": r.quantity_b,
                        "sku_a": r.sku_a,
                        "sku_b": r.sku_b,
                        "position_code_a": r.position_code_a,
                        "position_code_b": r.position_code_b,
                    }
                    for r in rows
                ]
                comp_payload["diff_rows_truncated"] = rows_truncated
            comparisons.append(comp_payload)

        jobs_payload = []
        raw_flags = []
        for job_id in job_ids:
            run = run_data[job_id]
            # Phase 3 keeps metadata aligned with existing job_metadata_dict fields.
            # TODO(phase4-metadata): add richer run metadata only when supported without extra data reads.
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
            raw_flags.append({"job_id": job_id, "truncated": run.raw_truncated})

        total_quantities = [run_data[job_id].metrics.total_quantity for job_id in job_ids]
        needs_review_counts = [run_data[job_id].metrics.needs_review_count for job_id in job_ids]
        consolidated_counts = [
            run_data[job_id].metrics.consolidated_positions for job_id in job_ids
        ]
        unknown_counts = [
            run_data[job_id].metrics.unknown_internal_code_count for job_id in job_ids
        ]

        durations = [job_execution_duration_seconds(run_data[jid].job) for jid in job_ids]
        dvals_non_null = [float(d) for d in durations if d is not None]
        if len(dvals_non_null) == len(job_ids):
            min_exec = min(dvals_non_null)
            max_exec = max(dvals_non_null)
        else:
            min_exec = None
            max_exec = None

        return {
            "inventory_id": command.inventory_id,
            "aisle_id": command.aisle_id,
            "workflow": "benchmark_compare_many",
            "read_only": True,
            "baseline_job_id": baseline_job_id,
            "jobs": jobs_payload,
            "comparisons": comparisons,
            "summary": {
                "job_count": len(job_ids),
                "baseline_job_id": baseline_job_id,
                "max_total_quantity": max(total_quantities),
                "min_total_quantity": min(total_quantities),
                "max_needs_review": max(needs_review_counts),
                "min_needs_review": min(needs_review_counts),
                "max_consolidated_positions": max(consolidated_counts),
                "min_consolidated_positions": min(consolidated_counts),
                "max_unknown_internal_code_count": max(unknown_counts),
                "min_unknown_internal_code_count": min(unknown_counts),
                "min_execution_time_seconds": min_exec,
                "max_execution_time_seconds": max_exec,
            },
            "raw_fetch_truncated": raw_flags,
        }
