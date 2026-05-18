"""Build inventory and aisle summary CSV row dicts for export."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.application.services.aisle_results_export_source import ui_aligned_rollup_service
from src.application.services.export_cost_helpers import job_total_cost_string
from src.application.services.export_inventory_collector import ExportInventoryOperationalData
from src.application.services.export_quantity_rollup import (
    ExportQuantityRollupService,
    InventoryExportRollupTotals,
)
from src.domain.jobs.entities import Job


class ExportSummaryBuilder:
    def __init__(self, rollup_service: ExportQuantityRollupService | None = None) -> None:
        self._rollup = rollup_service or ui_aligned_rollup_service()

    def build_rollups(self, data: ExportInventoryOperationalData) -> InventoryExportRollupTotals:
        inputs = [rb.rollup_input for bundle in data.aisle_bundles for rb in bundle.rows]
        aisle_ids = [a.id for a in data.aisles_in_order]
        return self._rollup.rollup_inventory(aisle_ids, inputs)

    def inventory_summary_row(
        self,
        data: ExportInventoryOperationalData,
        rollups: InventoryExportRollupTotals,
        *,
        exported_at: datetime | None = None,
        inventory_total_cost: str = "",
    ) -> dict[str, Any]:
        when = exported_at or datetime.now(timezone.utc)
        return {
            "Inventario": data.inventory.name,
            "Cliente": data.client_name,
            "Fecha de exportación": when.isoformat(),
            "Total de pasillos": rollups.total_aisles,
            "Total de filas exportadas": rollups.total_positions,
            "Ítems contados": rollups.valid_positions,
            "Filas excluidas del total": rollups.invalid_positions,
            "Posiciones con revisión pendiente": rollups.needs_review_count,
            "Total contabilizado": rollups.total_counted_quantity,
            "Costo total del inventario": inventory_total_cost,
        }

    def aisles_summary_rows(
        self,
        data: ExportInventoryOperationalData,
        rollups: InventoryExportRollupTotals,
        *,
        aisle_cost_by_id: dict[str, str] | None = None,
        last_updated_by_aisle: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        costs = aisle_cost_by_id or {}
        updated = last_updated_by_aisle or {}
        aisle_meta = {a.id: (seq, a) for seq, a in enumerate(data.aisles_in_order, start=1)}
        rows: list[dict[str, Any]] = []
        for totals in rollups.aisle_totals:
            seq, aisle = aisle_meta.get(totals.aisle_id, (0, None))
            if aisle is None:
                continue
            rows.append(
                {
                    "Inventario": data.inventory.name,
                    "Pasillo": aisle.code,
                    "Secuencia": seq,
                    "Proveedor": data.supplier_names_by_aisle_id.get(aisle.id, ""),
                    "Total de filas exportadas": totals.total_positions,
                    "Ítems contados": totals.valid_positions,
                    "Filas excluidas del total": totals.invalid_positions,
                    "Requieren revisión": totals.needs_review_count,
                    "Total contabilizado": totals.total_counted_quantity,
                    "Costo del pasillo": costs.get(aisle.id, ""),
                    "Última actualización": updated.get(aisle.id, ""),
                }
            )
        return rows

    @staticmethod
    def max_updated_at_for_bundle(bundle_rows: tuple) -> str:
        times = [rb.internal_row.get("updated_at", "") for rb in bundle_rows]
        return max((t for t in times if t), default="")

    @staticmethod
    def sum_aisle_job_costs(jobs: list[Job | None]) -> str:
        parts: list[str] = []
        for job in jobs:
            cost = job_total_cost_string(job)
            if cost:
                parts.append(cost)
        if not parts:
            return ""
        try:
            total = sum(float(p) for p in parts)
            return f"{total:.8f}".rstrip("0").rstrip(".")
        except ValueError:
            return ""
