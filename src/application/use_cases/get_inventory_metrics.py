"""
GetInventoryMetrics use case — v3.0 Épica 9.

Returns canonical inventory metrics per Documento técnico §9.6. Raises
InventoryNotFoundError if the inventory does not exist.
"""

from __future__ import annotations

from src.application.errors import InventoryNotFoundError
from src.application.ports.contracts import InventoryMetricsResult
from src.application.ports.repositories import InventoryRepository
from src.application.ports.services import MetricsCalculator


class GetInventoryMetricsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        metrics_calculator: MetricsCalculator,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._metrics_calculator = metrics_calculator

    def execute(self, inventory_id: str) -> InventoryMetricsResult:
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        return self._metrics_calculator.calculate_inventory_metrics(inventory_id)
