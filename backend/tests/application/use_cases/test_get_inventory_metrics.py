"""Tests for GetInventoryMetricsUseCase — Épica 9."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.errors import InventoryNotFoundError
from src.application.ports.contracts import InventoryMetricsResult
from src.application.ports.repositories import InventoryRepository
from src.application.ports.services import MetricsCalculator
from src.application.use_cases.inventories.get_inventory_metrics import GetInventoryMetricsUseCase
from src.domain.inventory.entities import Inventory, InventoryStatus


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventories: list[Inventory]) -> None:
        self._store = {inv.id: inv for inv in inventories}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubMetricsCalculator(MetricsCalculator):
    def __init__(self, result: InventoryMetricsResult) -> None:
        self._result = result

    def calculate_inventory_metrics(self, inventory_id: str) -> InventoryMetricsResult:
        return self._result


def test_get_metrics_returns_calculator_result_when_inventory_exists() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    metrics = InventoryMetricsResult(
        total_positions=10,
        total_reviewed_positions=8,
        auto_accepted_positions=5,
        corrected_positions=2,
        deleted_positions=1,
        success_rate=62.5,
        correction_rate=25.0,
        deletion_rate=12.5,
    )
    calculator = StubMetricsCalculator(metrics)
    use_case = GetInventoryMetricsUseCase(inventory_repo=inv_repo, metrics_calculator=calculator)

    result = use_case.execute("inv-1")

    assert result["total_positions"] == 10
    assert result["total_reviewed_positions"] == 8
    assert result["success_rate"] == 62.5


def test_get_metrics_raises_when_inventory_not_found() -> None:
    inv_repo = StubInventoryRepo([])
    calculator = StubMetricsCalculator(
        InventoryMetricsResult(total_positions=0, total_reviewed_positions=0)
    )
    use_case = GetInventoryMetricsUseCase(inventory_repo=inv_repo, metrics_calculator=calculator)

    with pytest.raises(InventoryNotFoundError):
        use_case.execute("nonexistent")
