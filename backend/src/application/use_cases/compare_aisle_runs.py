"""Phase 6 — read-only compare of two explicit aisle runs (benchmark workflow)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository, PositionRepository
from src.application.use_cases.benchmark_compare_support import (
    aggregate_metrics,
    build_compare_diff_rows,
    compute_compare_diff,
    job_metadata_dict,
    load_consolidated_for_job_slice,
    signatures_for_consolidated,
)

_DEFAULT_RAW_CAP = 2000
_MAX_DIFF_ROWS = 250


@dataclass(frozen=True)
class CompareAisleRunsCommand:
    inventory_id: str
    aisle_id: str
    job_a_id: str
    job_b_id: str


class CompareAisleRunsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        position_repo: PositionRepository,
        *,
        positions_aisle_raw_cap: int,
        diff_row_cap: int = _MAX_DIFF_ROWS,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._position_repo = position_repo
        self._raw_cap = max(1, int(positions_aisle_raw_cap))
        self._diff_row_cap = max(1, int(diff_row_cap))

    def _validate_job(self, job_id: str, aisle_id: str) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_type != "aisle" or job.target_id != aisle_id:
            raise JobDoesNotBelongToAisleError(
                f"Job {job_id} is not scoped to aisle {aisle_id}"
            )

    def _fetch_raw(self, aisle_id: str, job_id: str) -> tuple[List[Any], bool]:
        q = PositionListQuery(
            page=1,
            page_size=self._raw_cap,
            sort_by="created_at",
            sort_dir="asc",
            job_id=job_id,
        )
        rows = list(self._position_repo.list_by_aisle_query(aisle_id, q))
        truncated = len(rows) >= self._raw_cap
        return rows, truncated

    def execute(self, command: CompareAisleRunsCommand) -> dict[str, Any]:
        if command.job_a_id == command.job_b_id:
            # Valid trivial compare; still return symmetric payload.
            pass

        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None or aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )

        self._validate_job(command.job_a_id, command.aisle_id)
        self._validate_job(command.job_b_id, command.aisle_id)

        job_a = self._job_repo.get_by_id(command.job_a_id)
        job_b = self._job_repo.get_by_id(command.job_b_id)
        assert job_a is not None and job_b is not None

        raw_a, trunc_a = self._fetch_raw(command.aisle_id, command.job_a_id)
        raw_b, trunc_b = self._fetch_raw(command.aisle_id, command.job_b_id)

        cons_a = load_consolidated_for_job_slice(positions=raw_a)
        cons_b = load_consolidated_for_job_slice(positions=raw_b)

        sig_a = signatures_for_consolidated(cons_a)
        sig_b = signatures_for_consolidated(cons_b)

        metrics_a = aggregate_metrics(cons_a, raw_fetched=len(raw_a))
        metrics_b = aggregate_metrics(cons_b, raw_fetched=len(raw_b))
        diff = compute_compare_diff(sig_a, sig_b)
        diff_rows, diff_trunc = build_compare_diff_rows(
            sig_a, sig_b, max_rows=self._diff_row_cap
        )

        return {
            "inventory_id": command.inventory_id,
            "aisle_id": command.aisle_id,
            "workflow": "benchmark_compare",
            "read_only": True,
            "raw_fetch_truncated": {"job_a": trunc_a, "job_b": trunc_b},
            "run_a": {
                **job_metadata_dict(job_a),
                "metrics": {
                    "raw_rows_considered": metrics_a.raw_rows_considered,
                    "consolidated_positions": metrics_a.consolidated_positions,
                    "total_quantity": metrics_a.total_quantity,
                    "unknown_internal_code_count": metrics_a.unknown_internal_code_count,
                    "needs_review_count": metrics_a.needs_review_count,
                },
            },
            "run_b": {
                **job_metadata_dict(job_b),
                "metrics": {
                    "raw_rows_considered": metrics_b.raw_rows_considered,
                    "consolidated_positions": metrics_b.consolidated_positions,
                    "total_quantity": metrics_b.total_quantity,
                    "unknown_internal_code_count": metrics_b.unknown_internal_code_count,
                    "needs_review_count": metrics_b.needs_review_count,
                },
            },
            "diff_summary": {
                "keys_only_in_a": diff.keys_only_in_a,
                "keys_only_in_b": diff.keys_only_in_b,
                "keys_in_both": diff.keys_in_both,
                "quantity_changed": diff.quantity_changed,
                "sku_changed": diff.sku_changed,
                "position_code_changed": diff.position_code_changed,
            },
            "diff_rows": [
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
                for r in diff_rows
            ],
            "diff_rows_truncated": diff_trunc,
        }
