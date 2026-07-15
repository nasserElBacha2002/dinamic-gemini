"""
Inventory aggregation scope — operational vs historical aisle sets.

Operational rollups (quantities, positions, pending review, consolidates exports,
inventory status) use only active aisles.

Historical / cost rollups (jobs, LLM costs, tokens, observability, individual aisle
export) use all aisles — soft-deactivated rows stay in cost history.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.application.ports.repositories import AisleRepository
from src.domain.aisle.entities import Aisle


@dataclass(frozen=True)
class InventoryAggregationScope:
    """Aisle id sets for an inventory after resolving ``is_active``."""

    all_aisle_ids: frozenset[str]
    active_aisle_ids: frozenset[str]
    #: Full aisle entities for callers that need code / operational_job_id (all aisles).
    aisles: tuple[Aisle, ...]

    @property
    def operational_aisle_ids(self) -> frozenset[str]:
        return self.active_aisle_ids

    @property
    def historical_aisle_ids(self) -> frozenset[str]:
        return self.all_aisle_ids

    @property
    def operational_aisles(self) -> tuple[Aisle, ...]:
        return tuple(a for a in self.aisles if a.is_active)

    @property
    def historical_aisles(self) -> tuple[Aisle, ...]:
        return self.aisles


class InventoryAggregationScopeResolver:
    def __init__(self, aisle_repo: AisleRepository) -> None:
        self._aisle_repo = aisle_repo

    def resolve(self, inventory_id: str) -> InventoryAggregationScope:
        aisles = tuple(self._aisle_repo.list_by_inventory(inventory_id))
        return InventoryAggregationScope(
            all_aisle_ids=frozenset(a.id for a in aisles),
            active_aisle_ids=frozenset(a.id for a in aisles if a.is_active),
            aisles=aisles,
        )


def scope_from_aisles(aisles: Sequence[Aisle]) -> InventoryAggregationScope:
    """Build scope from an already-loaded aisle list (avoids a second repository round-trip)."""
    aisle_tuple = tuple(aisles)
    return InventoryAggregationScope(
        all_aisle_ids=frozenset(a.id for a in aisle_tuple),
        active_aisle_ids=frozenset(a.id for a in aisle_tuple if a.is_active),
        aisles=aisle_tuple,
    )
