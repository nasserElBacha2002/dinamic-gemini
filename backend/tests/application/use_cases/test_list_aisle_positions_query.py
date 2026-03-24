"""ListAislePositionsUseCase — filters, post-consolidation pagination (Sprint 1.4)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository


def _repos():
    now = datetime(2025, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    inv = Inventory("inv-1", "X", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-1", "inv-1", "A", AisleStatus.PROCESSED, now, now)
    aisle_repo.save(aisle)
    p_review = Position(
        "p1",
        "aisle-1",
        PositionStatus.DETECTED,
        0.5,
        True,
        None,
        now,
        now,
        detected_summary_json={"internal_code": "SKU-A", "final_quantity": 1},
    )
    p_ok = Position(
        "p2",
        "aisle-1",
        PositionStatus.DETECTED,
        0.9,
        False,
        "ev-1",
        now,
        now,
        detected_summary_json={"internal_code": "SKU-B", "final_quantity": 2},
    )
    pos_repo.save(p_review)
    pos_repo.save(p_ok)
    return inv_repo, aisle_repo, pos_repo, now


def test_list_aisle_positions_filters_by_needs_review() -> None:
    inv_repo, aisle_repo, pos_repo, _ = _repos()
    uc = ListAislePositionsUseCase(inv_repo, aisle_repo, pos_repo, positions_aisle_raw_cap=500)
    result = uc.execute(
        ListAislePositionsCommand(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            needs_review=True,
            page=1,
            page_size=50,
        )
    )
    assert len(result.positions) == 1
    assert result.positions[0].id == "p1"
    assert result.positions[0].needs_review is True


def test_list_aisle_positions_default_pagination_matches_explicit() -> None:
    inv_repo, aisle_repo, pos_repo, _ = _repos()
    uc = ListAislePositionsUseCase(inv_repo, aisle_repo, pos_repo, positions_aisle_raw_cap=500)
    explicit = uc.execute(
        ListAislePositionsCommand(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            page=1,
            page_size=25,
        )
    )
    implicit = uc.execute(ListAislePositionsCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert [p.id for p in explicit.positions] == [p.id for p in implicit.positions]
