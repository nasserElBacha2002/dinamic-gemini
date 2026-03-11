"""Tests for InventoryMetricsService — Épica 9."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import AisleRepository, PositionRepository
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.services.inventory_metrics_service import InventoryMetricsService


class StubAisleRepo(AisleRepository):
    def __init__(self, aisles: list[Aisle]) -> None:
        self._aisles = aisles

    def save(self, aisle: Aisle) -> None:
        raise NotImplementedError

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        for a in self._aisles:
            if a.id == aisle_id:
                return a
        return None

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._aisles if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        for a in self._aisles:
            if a.inventory_id == inventory_id and a.code == code:
                return a
        return None


class StubPositionRepo(PositionRepository):
    def __init__(self, positions: list[Position]) -> None:
        self._positions = positions

    def save(self, position: Position) -> None:
        raise NotImplementedError

    def get_by_id(self, position_id: str) -> Optional[Position]:
        for p in self._positions:
            if p.id == position_id:
                return p
        return None

    def list_by_aisle(
        self,
        aisle_id: str,
        status: Optional[str] = None,
        needs_review: Optional[bool] = None,
        min_confidence: Optional[float] = None,
        sku_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> Sequence[Position]:
        return []

    def list_by_aisle_query(self, aisle_id: str, query: Optional[PositionListQuery] = None) -> Sequence[Position]:
        return []

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        aid_set = set(aisle_ids)
        return [p for p in self._positions if p.aisle_id in aid_set]


def _position(pid: str, aisle_id: str, status: PositionStatus) -> Position:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    return Position(
        id=pid,
        aisle_id=aisle_id,
        status=status,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
    )


def test_metrics_zero_positions_returns_zero_rates() -> None:
    """When inventory has no positions, total_positions and total_reviewed are 0, rates are 0."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo([aisle])
    position_repo = StubPositionRepo([])
    service = InventoryMetricsService(aisle_repo=aisle_repo, position_repo=position_repo)

    result = service.calculate_inventory_metrics("inv-1")

    assert result["total_positions"] == 0
    assert result["total_reviewed_positions"] == 0
    assert result["auto_accepted_positions"] == 0
    assert result["corrected_positions"] == 0
    assert result["deleted_positions"] == 0
    assert result["success_rate"] == 0.0
    assert result["correction_rate"] == 0.0
    assert result["deletion_rate"] == 0.0


def test_metrics_zero_reviewed_positions_returns_zero_rates() -> None:
    """When all positions are detected (non-terminal), total_reviewed is 0, rates are 0."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    positions = [
        _position("p1", "a1", PositionStatus.DETECTED),
        _position("p2", "a1", PositionStatus.DETECTED),
    ]
    aisle_repo = StubAisleRepo([aisle])
    position_repo = StubPositionRepo(positions)
    service = InventoryMetricsService(aisle_repo=aisle_repo, position_repo=position_repo)

    result = service.calculate_inventory_metrics("inv-1")

    assert result["total_positions"] == 2
    assert result["total_reviewed_positions"] == 0
    assert result["success_rate"] == 0.0
    assert result["correction_rate"] == 0.0
    assert result["deletion_rate"] == 0.0


def test_metrics_mixed_statuses_counts_correctly() -> None:
    """Reviewed, corrected, deleted are counted; detected are not in total_reviewed."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    positions = [
        _position("p1", "a1", PositionStatus.DETECTED),
        _position("p2", "a1", PositionStatus.REVIEWED),
        _position("p3", "a1", PositionStatus.REVIEWED),
        _position("p4", "a1", PositionStatus.CORRECTED),
        _position("p5", "a1", PositionStatus.DELETED),
    ]
    aisle_repo = StubAisleRepo([aisle])
    position_repo = StubPositionRepo(positions)
    service = InventoryMetricsService(aisle_repo=aisle_repo, position_repo=position_repo)

    result = service.calculate_inventory_metrics("inv-1")

    assert result["total_positions"] == 5
    assert result["total_reviewed_positions"] == 4
    assert result["auto_accepted_positions"] == 2
    assert result["corrected_positions"] == 1
    assert result["deleted_positions"] == 1
    assert result["success_rate"] == 50.0
    assert result["correction_rate"] == 25.0
    assert result["deletion_rate"] == 25.0


def test_metrics_only_other_inventory_aisles_excluded() -> None:
    """Positions from other inventories' aisles are not included."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle1 = Aisle("a1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    aisle2 = Aisle("a2", "inv-2", "A02", AisleStatus.CREATED, now, now)
    positions = [
        _position("p1", "a1", PositionStatus.REVIEWED),
        _position("p2", "a2", PositionStatus.REVIEWED),
    ]
    aisle_repo = StubAisleRepo([aisle1, aisle2])
    position_repo = StubPositionRepo(positions)
    service = InventoryMetricsService(aisle_repo=aisle_repo, position_repo=position_repo)

    result = service.calculate_inventory_metrics("inv-1")

    assert result["total_positions"] == 1
    assert result["total_reviewed_positions"] == 1
    assert result["auto_accepted_positions"] == 1
    assert result["success_rate"] == 100.0


def test_metrics_inventory_with_no_aisles_returns_zeros() -> None:
    """When inventory has no aisles, list_by_aisles([]) is used; result is all zeros."""
    aisle_repo = StubAisleRepo([])
    position_repo = StubPositionRepo([])
    service = InventoryMetricsService(aisle_repo=aisle_repo, position_repo=position_repo)

    result = service.calculate_inventory_metrics("inv-empty")

    assert result["total_positions"] == 0
    assert result["total_reviewed_positions"] == 0
    assert result["auto_accepted_positions"] == 0
    assert result["corrected_positions"] == 0
    assert result["deleted_positions"] == 0
    assert result["success_rate"] == 0.0
    assert result["correction_rate"] == 0.0
    assert result["deletion_rate"] == 0.0
