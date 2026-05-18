"""Centralized export quantity totals and row eligibility (v3 inventory export refactor)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.domain.positions.entities import PositionStatus
from src.domain.traceability import TraceabilityStatus

ExportExclusionReason = Literal[
    "deleted",
    "traceability_invalid",
]


@dataclass(frozen=True)
class ExportQuantityRollupConfig:
    """Controls whether traceability-invalid rows count toward totals.

    Legacy CSV exports do not use this service. Business/summary exports default to excluding
    traceability-invalid rows from counted totals while still listing them in operational CSVs.
    """

    exclude_traceability_invalid_from_totals: bool = True


@dataclass(frozen=True)
class ExportRollupRowInput:
    position_id: str
    aisle_id: str
    position_status: str
    traceability_status: str | None
    needs_review: bool
    final_quantity: int


@dataclass(frozen=True)
class ExportRowRollupResult:
    included_in_totals: bool
    exclusion_reason: ExportExclusionReason | None
    final_quantity_for_totals: int


@dataclass(frozen=True)
class AisleExportRollupTotals:
    aisle_id: str
    total_positions: int
    valid_positions: int
    invalid_positions: int
    needs_review_count: int
    total_counted_quantity: int


@dataclass(frozen=True)
class InventoryExportRollupTotals:
    total_aisles: int
    total_positions: int
    valid_positions: int
    invalid_positions: int
    needs_review_count: int
    total_counted_quantity: int
    aisle_totals: tuple[AisleExportRollupTotals, ...]


def _normalized_status(value: str | None) -> str:
    return (value or "").strip().lower()


def is_traceability_invalid(traceability_status: str | None) -> bool:
    return _normalized_status(traceability_status) == TraceabilityStatus.INVALID.value


def is_position_deleted(position_status: str) -> bool:
    return _normalized_status(position_status) == PositionStatus.DELETED.value


class ExportQuantityRollupService:
    """Single source of truth for export totals and per-row inclusion metadata."""

    def __init__(self, config: ExportQuantityRollupConfig | None = None) -> None:
        self._config = config or ExportQuantityRollupConfig()

    def rollup_row(self, row: ExportRollupRowInput) -> ExportRowRollupResult:
        if is_position_deleted(row.position_status):
            return ExportRowRollupResult(
                included_in_totals=False,
                exclusion_reason="deleted",
                final_quantity_for_totals=0,
            )
        if (
            self._config.exclude_traceability_invalid_from_totals
            and is_traceability_invalid(row.traceability_status)
        ):
            return ExportRowRollupResult(
                included_in_totals=False,
                exclusion_reason="traceability_invalid",
                final_quantity_for_totals=0,
            )
        qty = max(0, int(row.final_quantity))
        return ExportRowRollupResult(
            included_in_totals=True,
            exclusion_reason=None,
            final_quantity_for_totals=qty,
        )

    def rollup_aisle(self, aisle_id: str, rows: list[ExportRollupRowInput]) -> AisleExportRollupTotals:
        aisle_rows = [r for r in rows if r.aisle_id == aisle_id]
        return self._rollup_rows(aisle_id, aisle_rows)

    def rollup_inventory(
        self,
        aisle_ids_in_order: list[str],
        rows: list[ExportRollupRowInput],
    ) -> InventoryExportRollupTotals:
        aisle_totals = [self.rollup_aisle(aid, rows) for aid in aisle_ids_in_order]
        return InventoryExportRollupTotals(
            total_aisles=len(aisle_ids_in_order),
            total_positions=sum(t.total_positions for t in aisle_totals),
            valid_positions=sum(t.valid_positions for t in aisle_totals),
            invalid_positions=sum(t.invalid_positions for t in aisle_totals),
            needs_review_count=sum(t.needs_review_count for t in aisle_totals),
            total_counted_quantity=sum(t.total_counted_quantity for t in aisle_totals),
            aisle_totals=tuple(aisle_totals),
        )

    def _rollup_rows(self, aisle_id: str, rows: list[ExportRollupRowInput]) -> AisleExportRollupTotals:
        valid = 0
        invalid = 0
        needs_review = 0
        total_qty = 0
        for row in rows:
            meta = self.rollup_row(row)
            if meta.included_in_totals:
                valid += 1
                total_qty += meta.final_quantity_for_totals
            else:
                invalid += 1
            if row.needs_review:
                needs_review += 1
        return AisleExportRollupTotals(
            aisle_id=aisle_id,
            total_positions=len(rows),
            valid_positions=valid,
            invalid_positions=invalid,
            needs_review_count=needs_review,
            total_counted_quantity=total_qty,
        )
