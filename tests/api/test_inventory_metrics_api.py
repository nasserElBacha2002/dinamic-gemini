"""API tests for GET /api/v3/inventories/{inventory_id}/metrics — Épica 9."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import get_get_inventory_metrics_use_case, get_inventory_repo
from src.api.server import app
from src.application.use_cases.get_inventory_metrics import GetInventoryMetricsUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.services.inventory_metrics_service import InventoryMetricsService


def _seed_inventory_with_positions():
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-metrics-1", "WH Metrics", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-m1", "inv-metrics-1", "M01", AisleStatus.CREATED, now, now)
    positions = [
        Position("pos-m1", "aisle-m1", PositionStatus.REVIEWED, 0.9, False, None, now, now),
        Position("pos-m2", "aisle-m1", PositionStatus.CORRECTED, 0.8, False, None, now, now),
        Position("pos-m3", "aisle-m1", PositionStatus.DETECTED, 0.7, True, None, now, now),
    ]
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    inv_repo.save(inv)
    aisle_repo.save(aisle)
    for p in positions:
        position_repo.save(p)
    metrics_calculator = InventoryMetricsService(aisle_repo=aisle_repo, position_repo=position_repo)
    use_case = GetInventoryMetricsUseCase(inventory_repo=inv_repo, metrics_calculator=metrics_calculator)
    return use_case, inv_repo


def test_get_inventory_metrics_returns_200_and_body() -> None:
    use_case, inv_repo = _seed_inventory_with_positions()
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_get_inventory_metrics_use_case] = lambda: use_case
    client = TestClient(app)
    try:
        resp = client.get("/api/v3/inventories/inv-metrics-1/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_positions"] == 3
        assert data["total_reviewed_positions"] == 2
        assert data["auto_accepted_positions"] == 1
        assert data["corrected_positions"] == 1
        assert data["deleted_positions"] == 0
        assert data["success_rate"] == 50.0
        assert data["correction_rate"] == 50.0
        assert data["deletion_rate"] == 0.0
    finally:
        app.dependency_overrides.clear()


def test_get_inventory_metrics_returns_404_when_inventory_missing() -> None:
    use_case, inv_repo = _seed_inventory_with_positions()
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_get_inventory_metrics_use_case] = lambda: use_case
    client = TestClient(app)
    try:
        resp = client.get("/api/v3/inventories/nonexistent-id/metrics")
        assert resp.status_code == 404
        assert "not found" in (resp.json().get("detail") or "").lower()
    finally:
        app.dependency_overrides.clear()
