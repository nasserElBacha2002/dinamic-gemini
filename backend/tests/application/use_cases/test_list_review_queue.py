"""ListReviewQueueUseCase — cross-inventory needs_review listing (Sprint 1.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from src.application.ports.contracts import ReviewQueueQuery
from src.application.use_cases.list_review_queue import ListReviewQueueUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository

UTC = timezone.utc


class CountingProductRepo(MemoryProductRecordRepository):
    def __init__(self) -> None:
        super().__init__()
        self.list_by_position_calls = 0
        self.list_by_position_ids_calls = 0

    def list_by_position(self, position_id: str) -> Sequence[ProductRecord]:
        self.list_by_position_calls += 1
        return super().list_by_position(position_id)

    def list_by_position_ids(self, position_ids: Sequence[str]) -> Sequence[ProductRecord]:
        self.list_by_position_ids_calls += 1
        return super().list_by_position_ids(position_ids)


def test_review_queue_filters_and_pages() -> None:
    now = datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    product_repo = CountingProductRepo()

    inv_repo.save(Inventory("inv-a", "Alpha", InventoryStatus.DRAFT, now, now))
    inv_repo.save(Inventory("inv-b", "Beta", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-a", "inv-a", "A1", AisleStatus.CREATED, now, now))
    aisle_repo.save(Aisle("aisle-b", "inv-b", "B1", AisleStatus.CREATED, now, now))

    pos_repo.save(
        Position(
            "p1",
            "aisle-a",
            PositionStatus.DETECTED,
            0.4,
            True,
            None,
            now,
            now,
        )
    )
    pos_repo.save(
        Position(
            "p2",
            "aisle-b",
            PositionStatus.DETECTED,
            0.9,
            True,
            None,
            now,
            now,
        )
    )
    pos_repo.save(
        Position(
            "p3",
            "aisle-b",
            PositionStatus.DETECTED,
            0.95,
            False,
            None,
            now,
            now,
        )
    )

    uc = ListReviewQueueUseCase(inv_repo, aisle_repo, pos_repo, product_repo)
    rows, total, summary = uc.execute(ReviewQueueQuery(inventory_id="inv-b", page=1, page_size=10))
    assert total == 1
    assert summary.pending_review == 1
    assert len(rows) == 1
    assert rows[0].position.id == "p2"
    assert rows[0].inventory_name == "Beta"
    assert rows[0].aisle_code == "B1"
    assert rows[0].primary_product is None
    assert product_repo.list_by_position_ids_calls == 1
    assert product_repo.list_by_position_calls == 0


def test_review_queue_out_of_range_page_returns_empty_slice() -> None:
    now = datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    inv_repo.save(Inventory("inv-x", "X", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-x", "inv-x", "X1", AisleStatus.CREATED, now, now))
    pos_repo.save(
        Position("px", "aisle-x", PositionStatus.DETECTED, 0.5, True, None, now, now)
    )
    uc = ListReviewQueueUseCase(inv_repo, aisle_repo, pos_repo, product_repo)
    rows, total, summary = uc.execute(ReviewQueueQuery(page=99, page_size=10))
    assert total == 1
    assert summary.pending_review == 1
    assert rows == []


def test_review_queue_prefers_primary_product_for_sku_and_qty_zero_filter() -> None:
    now = datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()

    inv_repo.save(Inventory("inv-a", "Alpha", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-a", "inv-a", "A1", AisleStatus.CREATED, now, now))
    pos_repo.save(
        Position(
            "p1",
            "aisle-a",
            PositionStatus.DETECTED,
            0.8,
            True,
            "ev-1",
            now,
            now,
            detected_summary_json={"internal_code": "OLD-SKU", "final_quantity": 7},
        )
    )
    product_repo.save(
        ProductRecord(
            id="prod-1",
            position_id="p1",
            sku="CANON-SKU",
            description="",
            detected_quantity=5,
            corrected_quantity=0,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )

    uc = ListReviewQueueUseCase(inv_repo, aisle_repo, pos_repo, product_repo)
    rows, total, summary = uc.execute(ReviewQueueQuery(sku_contains="canon", qty_zero=True))

    assert total == 1
    assert len(rows) == 1
    assert rows[0].position.id == "p1"
    assert summary.qty_zero == 1
    assert rows[0].primary_product is not None
    assert rows[0].primary_product.sku == "CANON-SKU"
    assert rows[0].primary_product.corrected_quantity == 0


def test_review_queue_keeps_aggregated_snapshot_qty_zero_fallback() -> None:
    now = datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()

    inv_repo.save(Inventory("inv-a", "Alpha", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-a", "inv-a", "A1", AisleStatus.CREATED, now, now))
    pos_repo.save(
        Position(
            "p1",
            "aisle-a",
            PositionStatus.DETECTED,
            0.8,
            True,
            "ev-1",
            now,
            now,
            detected_summary_json={
                "internal_code": "AGG-SKU",
                "final_quantity": 0,
                "aggregated_from_ids": ["p1", "p2"],
            },
        )
    )
    product_repo.save(
        ProductRecord(
            id="prod-1",
            position_id="p1",
            sku="AGG-SKU",
            description="",
            detected_quantity=9,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )

    uc = ListReviewQueueUseCase(inv_repo, aisle_repo, pos_repo, product_repo)
    rows, total, summary = uc.execute(ReviewQueueQuery(qty_zero=True))

    assert total == 1
    assert len(rows) == 1
    assert rows[0].position.id == "p1"
    assert summary.qty_zero == 1
    assert rows[0].primary_product is not None
    assert rows[0].primary_product.sku == "AGG-SKU"
