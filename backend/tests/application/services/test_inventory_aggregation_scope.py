"""Tests for InventoryAggregationScope — operational vs historical aisle sets."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.inventory_aggregation_scope import (
    InventoryAggregationScopeResolver,
    scope_from_aisles,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _aisle(
    aid: str,
    *,
    code: str,
    is_active: bool = True,
    status: AisleStatus = AisleStatus.COMPLETED,
) -> Aisle:
    return Aisle(
        id=aid,
        inventory_id="I1",
        code=code,
        status=status,
        created_at=NOW,
        updated_at=NOW,
        is_active=is_active,
    )


def test_scope_from_aisles_splits_active_and_all() -> None:
    a = _aisle("A", code="A", is_active=True)
    b = _aisle("B", code="B", is_active=False)
    scope = scope_from_aisles([a, b])

    assert scope.all_aisle_ids == frozenset({"A", "B"})
    assert scope.active_aisle_ids == frozenset({"A"})
    assert scope.operational_aisle_ids == frozenset({"A"})
    assert scope.historical_aisle_ids == frozenset({"A", "B"})
    assert [x.id for x in scope.operational_aisles] == ["A"]
    assert [x.id for x in scope.historical_aisles] == ["A", "B"]


def test_scope_resolver_loads_from_repo() -> None:
    repo = MemoryAisleRepository()
    repo.save(_aisle("A", code="A", is_active=True))
    repo.save(_aisle("B", code="B", is_active=False))
    scope = InventoryAggregationScopeResolver(repo).resolve("I1")

    assert scope.active_aisle_ids == frozenset({"A"})
    assert scope.all_aisle_ids == frozenset({"A", "B"})


def test_scope_no_active_aisles() -> None:
    scope = scope_from_aisles([_aisle("B", code="B", is_active=False)])
    assert scope.active_aisle_ids == frozenset()
    assert scope.operational_aisles == ()
    assert scope.all_aisle_ids == frozenset({"B"})
