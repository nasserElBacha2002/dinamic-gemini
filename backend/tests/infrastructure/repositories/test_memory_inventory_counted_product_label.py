"""Aisle-scoped label_id claim concurrency / idempotency."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.inventory_counted_product_label_repository import (
    InventoryCountedProductLabel,
)
from src.infrastructure.repositories.memory_inventory_counted_product_label_repository import (
    MemoryInventoryCountedProductLabelRepository,
)


def _row(
    label_id: str,
    product_id: str = "p1",
    *,
    aisle_id: str = "aisle-1",
    inventory_id: str = "inv-1",
) -> InventoryCountedProductLabel:
    return InventoryCountedProductLabel(
        id=f"claim-{product_id}",
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        label_id=label_id,
        first_product_record_id=product_id,
        first_source_asset_id="asset-1",
        first_job_id="job-1",
        first_position_id="pos-1",
        created_at=datetime.now(timezone.utc),
    )


def test_claim_once_per_aisle_label() -> None:
    repo = MemoryInventoryCountedProductLabelRepository()
    assert repo.try_claim(_row("A1B2C3D4E5", "p1")) is True
    assert repo.try_claim(_row("A1B2C3D4E5", "p2")) is False
    assert repo.get("aisle-1", "A1B2C3D4E5") is not None
    assert repo.get("aisle-1", "A1B2C3D4E5").first_product_record_id == "p1"


def test_same_label_different_aisle_same_inventory_allowed() -> None:
    repo = MemoryInventoryCountedProductLabelRepository()
    a = _row("A1B2C3D4E5", "p1", aisle_id="aisle-1")
    b = _row("A1B2C3D4E5", "p9", aisle_id="aisle-2")
    assert repo.try_claim(a) is True
    assert repo.try_claim(b) is True
    assert repo.get("aisle-1", "A1B2C3D4E5").first_product_record_id == "p1"
    assert repo.get("aisle-2", "A1B2C3D4E5").first_product_record_id == "p9"


def test_same_label_different_inventory_allowed() -> None:
    repo = MemoryInventoryCountedProductLabelRepository()
    a = _row("A1B2C3D4E5", "p1", inventory_id="inv-1", aisle_id="aisle-1")
    b = _row("A1B2C3D4E5", "p9", inventory_id="inv-2", aisle_id="aisle-9")
    assert repo.try_claim(a) is True
    assert repo.try_claim(b) is True
