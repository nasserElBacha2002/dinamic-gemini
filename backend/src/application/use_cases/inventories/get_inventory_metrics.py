"""
GetInventoryMetrics use case — v3.0 Épica 9 (tenant-scoped Stage 2).

Returns canonical inventory metrics per Documento técnico §9.6. Raises
InventoryNotFoundError if the inventory does not exist or is not visible.
"""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.contracts import InventoryMetricsResult
from src.application.ports.repositories import InventoryRepository
from src.application.ports.services import MetricsCalculator
from src.application.services.inventory_access_policy import InventoryAccessPolicy


class GetInventoryMetricsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        metrics_calculator: MetricsCalculator,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._metrics_calculator = metrics_calculator
        self._policy = InventoryAccessPolicy(inventory_repo)

    def execute(self, inventory_id: str, principal: AccessPrincipal) -> InventoryMetricsResult:
        self._policy.require_inventory(inventory_id, principal)
        return self._metrics_calculator.calculate_inventory_metrics(inventory_id)
