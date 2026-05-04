"""
Inventory metrics calculator — v3.0 Épica 9.

Implements MetricsCalculator per Documento técnico §9.6. Computes metrics from
persisted positions (all positions in the inventory's aisles). Terminal states
(reviewed, corrected, deleted) count toward total_reviewed; success_rate and
rates use total_reviewed as denominator; when total_reviewed is 0, rates are 0.

Returned dict includes all keys required by §9.6 / InventoryMetricsResponse.
Rates are rounded to 2 decimal places and may not sum to 100 due to rounding.
"""

from __future__ import annotations

from src.application.ports.contracts import InventoryMetricsResult
from src.application.ports.repositories import AisleRepository, PositionRepository
from src.application.ports.services import MetricsCalculator
from src.domain.positions.entities import PositionStatus

# Terminal statuses: positions that have been through manual review (Documento técnico §9.6).
_TERMINAL_STATUSES = frozenset(
    {
        PositionStatus.REVIEWED.value,
        PositionStatus.CORRECTED.value,
        PositionStatus.DELETED.value,
    }
)


class InventoryMetricsService(MetricsCalculator):
    """Computes inventory metrics from aisle and position repositories."""

    def __init__(self, aisle_repo: AisleRepository, position_repo: PositionRepository) -> None:
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo

    def calculate_inventory_metrics(self, inventory_id: str) -> InventoryMetricsResult:
        aisles = self._aisle_repo.list_by_inventory(inventory_id)
        aisle_ids = [a.id for a in aisles]
        positions = self._position_repo.list_by_aisles(aisle_ids)

        total_positions = len(positions)
        reviewed_positions = [p for p in positions if p.status.value in _TERMINAL_STATUSES]
        total_reviewed = len(reviewed_positions)

        auto_accepted = sum(
            1 for p in reviewed_positions if p.status.value == PositionStatus.REVIEWED.value
        )
        corrected = sum(
            1 for p in reviewed_positions if p.status.value == PositionStatus.CORRECTED.value
        )
        deleted = sum(
            1 for p in reviewed_positions if p.status.value == PositionStatus.DELETED.value
        )

        if total_reviewed > 0:
            success_rate = round(auto_accepted / total_reviewed * 100, 2)
            correction_rate = round(corrected / total_reviewed * 100, 2)
            deletion_rate = round(deleted / total_reviewed * 100, 2)
        else:
            success_rate = 0.0
            correction_rate = 0.0
            deletion_rate = 0.0

        return InventoryMetricsResult(
            total_positions=total_positions,
            total_reviewed_positions=total_reviewed,
            auto_accepted_positions=auto_accepted,
            corrected_positions=corrected,
            deleted_positions=deleted,
            success_rate=success_rate,
            correction_rate=correction_rate,
            deletion_rate=deletion_rate,
        )
