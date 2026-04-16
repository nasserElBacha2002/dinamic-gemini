"""Phase 6 — explicit benchmark exports (single run slice or compare table)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from src.application.errors import (
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.inventory_processing_mode import (
    require_test_inventory_for_experimental_features,
)
from src.application.mappers.inventory_export_rows import (
    export_position_sort_key,
    position_to_operational_export_row_dict,
)
from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.csv_inventory_exporter import CsvInventoryExporter, INVENTORY_RESULTS_CSV_FIELDS
from src.application.services.display_primary_product import select_display_primary_product
from src.application.services.position_sku_consolidation import consolidate_positions_by_sku
from src.application.use_cases.benchmark_compare_support import CompareDiffRow, compare_csv_row_dict
from src.application.use_cases.compare_aisle_runs import CompareAisleRunsCommand, CompareAisleRunsUseCase
from src.domain.positions.entities import PositionStatus

BENCHMARK_RUN_EXTRA_FIELDS: tuple[str, ...] = (
    "benchmark_run_job_id",
    "benchmark_provider_name",
    "benchmark_model_name",
    "benchmark_prompt_key",
    "benchmark_prompt_version",
)

BENCHMARK_RUN_CSV_FIELDS: tuple[str, ...] = INVENTORY_RESULTS_CSV_FIELDS + BENCHMARK_RUN_EXTRA_FIELDS

BENCHMARK_COMPARE_CSV_FIELDS: tuple[str, ...] = (
    "match_key",
    "side",
    "quantity_a",
    "quantity_b",
    "delta_quantity",
    "sku_a",
    "sku_b",
    "position_code_a",
    "position_code_b",
)


@dataclass(frozen=True)
class ExportAisleBenchmarkRunCommand:
    inventory_id: str
    aisle_id: str
    run_job_id: str


class ExportAisleBenchmarkRunCsvUseCase:
    """Operational-shaped CSV rows for one explicit job slice, plus benchmark metadata columns."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        *,
        positions_aisle_raw_cap: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._raw_cap = max(1, int(positions_aisle_raw_cap))

    def _ensure_scope(self, command: ExportAisleBenchmarkRunCommand) -> None:
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
        job = self._job_repo.get_by_id(command.run_job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {command.run_job_id}")
        if job.target_type != "aisle" or job.target_id != command.aisle_id:
            raise JobDoesNotBelongToAisleError(
                f"Job {command.run_job_id} is not scoped to aisle {command.aisle_id}"
            )

    def execute_csv(self, command: ExportAisleBenchmarkRunCommand) -> str:
        self._ensure_scope(command)
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        job = self._job_repo.get_by_id(command.run_job_id)
        assert inv is not None and aisle is not None and job is not None

        q = PositionListQuery(
            page=1,
            page_size=self._raw_cap,
            sort_by="created_at",
            sort_dir="asc",
            job_id=command.run_job_id,
        )
        raw = list(self._position_repo.list_by_aisle_query(command.aisle_id, q))
        candidates = [p for p in raw if p.status != PositionStatus.DELETED]
        consolidated = consolidate_positions_by_sku(candidates)
        consolidated_sorted = sorted(consolidated, key=export_position_sort_key)

        rows: List[dict[str, Any]] = []
        for seq, p in enumerate(consolidated_sorted, start=1):
            products = self._product_record_repo.list_by_position(p.id)
            primary = select_display_primary_product(products)
            row = position_to_operational_export_row_dict(inv, aisle, seq, p, primary)
            row.update(
                {
                    "benchmark_run_job_id": job.id,
                    "benchmark_provider_name": job.provider_name or "",
                    "benchmark_model_name": job.model_name or "",
                    "benchmark_prompt_key": job.prompt_key or "",
                    "benchmark_prompt_version": job.prompt_version or "",
                }
            )
            rows.append(row)

        return CsvInventoryExporter.to_csv(rows, fieldnames=BENCHMARK_RUN_CSV_FIELDS)


class ExportAisleBenchmarkCompareCsvUseCase:
    """CSV for compare summary rows (explicit job_a / job_b)."""

    def __init__(self, compare_uc: CompareAisleRunsUseCase) -> None:
        self._compare_uc = compare_uc

    def execute_csv(self, command: CompareAisleRunsCommand) -> str:
        payload = self._compare_uc.execute(command)
        diff_rows = payload["diff_rows"]
        rows = [
            compare_csv_row_dict(
                CompareDiffRow(
                    match_key=str(r["match_key"]),
                    side=str(r["side"]),
                    quantity_a=r.get("quantity_a"),
                    quantity_b=r.get("quantity_b"),
                    sku_a=r.get("sku_a"),
                    sku_b=r.get("sku_b"),
                    position_code_a=r.get("position_code_a"),
                    position_code_b=r.get("position_code_b"),
                )
            )
            for r in diff_rows
        ]
        return CsvInventoryExporter.to_csv(rows, fieldnames=BENCHMARK_COMPARE_CSV_FIELDS)
