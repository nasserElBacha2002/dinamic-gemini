"""Tests for UpdateProductQuantityUseCase — Épica 8."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

import pytest

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    PositionNotFoundError,
    ProductNotFoundError,
)
from src.application.use_cases.update_product_quantity import UpdateProductQuantityUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction, ReviewActionType


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo:
    def __init__(self, inv: Optional[Inventory] = None) -> None:
        self._store = {} if inv is None else {inv.id: inv}

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        return self._store.get(inventory_id)


class StubAisleRepo:
    def __init__(self, aisle: Optional[Aisle] = None) -> None:
        self._store = {} if aisle is None else {aisle.id: aisle}

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)


class StubPositionRepo:
    def __init__(self, position: Optional[Position] = None) -> None:
        self._store = {} if position is None else {position.id: position}

    def get_by_id(self, position_id: str) -> Optional[Position]:
        return self._store.get(position_id)

    def save(self, position: Position) -> None:
        self._store[position.id] = position


class StubProductRepo:
    def __init__(self, product: Optional[ProductRecord] = None) -> None:
        self._store = {} if product is None else {product.id: product}

    def get_by_id(self, product_id: str) -> Optional[ProductRecord]:
        return self._store.get(product_id)

    def save(self, product: ProductRecord) -> None:
        self._store[product.id] = product


class StubReviewRepo:
    def __init__(self) -> None:
        self._actions: list[ReviewAction] = []

    def save(self, review: ReviewAction) -> None:
        self._actions.append(review)

    def list_by_position(self, position_id: str) -> Sequence[ReviewAction]:
        return [a for a in self._actions if a.position_id == position_id]


def test_update_quantity_sets_corrected_and_creates_audit() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    position = Position(
        id="pos-1",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
    )
    product = ProductRecord(
        id="prod-1",
        position_id="pos-1",
        sku="SKU-X",
        description="Item X",
        detected_quantity=5,
        corrected_quantity=None,
        confidence=0.95,
        created_at=now,
        updated_at=now,
    )
    inv_repo = StubInventoryRepo(inv)
    aisle_repo = StubAisleRepo(aisle)
    position_repo = StubPositionRepo(position)
    product_repo = StubProductRepo(product)
    review_repo = StubReviewRepo()
    clock = FixedClock(now)

    use_case = UpdateProductQuantityUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
        review_repo=review_repo,
        clock=clock,
    )
    use_case.execute("inv-1", "aisle-1", "pos-1", "prod-1", 10)

    updated_product = product_repo.get_by_id("prod-1")
    assert updated_product is not None
    assert updated_product.detected_quantity == 5
    assert updated_product.corrected_quantity == 10
    updated_position = position_repo.get_by_id("pos-1")
    assert updated_position is not None
    assert updated_position.status == PositionStatus.CORRECTED
    actions = review_repo.list_by_position("pos-1")
    assert len(actions) == 1
    assert actions[0].action_type == ReviewActionType.UPDATE_QUANTITY
    assert actions[0].before_json.get("corrected_quantity") is None
    assert actions[0].after_json.get("corrected_quantity") == 10


def test_update_quantity_negative_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    position = Position(
        id="pos-1", aisle_id="aisle-1", status=PositionStatus.DETECTED,
        confidence=0.9, needs_review=True, primary_evidence_id=None,
        created_at=now, updated_at=now,
    )
    product = ProductRecord(
        id="prod-1", position_id="pos-1", sku="X", description=None,
        detected_quantity=1, corrected_quantity=None, confidence=0.9,
        created_at=now, updated_at=now,
    )
    use_case = UpdateProductQuantityUseCase(
        inventory_repo=StubInventoryRepo(inv),
        aisle_repo=StubAisleRepo(aisle),
        position_repo=StubPositionRepo(position),
        product_record_repo=StubProductRepo(product),
        review_repo=StubReviewRepo(),
        clock=FixedClock(now),
    )
    with pytest.raises(ValueError, match="non-negative"):
        use_case.execute("inv-1", "aisle-1", "pos-1", "prod-1", -1)


def test_update_quantity_product_not_found_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    position = Position(
        id="pos-1", aisle_id="aisle-1", status=PositionStatus.DETECTED,
        confidence=0.9, needs_review=True, primary_evidence_id=None,
        created_at=now, updated_at=now,
    )
    use_case = UpdateProductQuantityUseCase(
        inventory_repo=StubInventoryRepo(inv),
        aisle_repo=StubAisleRepo(aisle),
        position_repo=StubPositionRepo(position),
        product_record_repo=StubProductRepo(None),
        review_repo=StubReviewRepo(),
        clock=FixedClock(now),
    )
    with pytest.raises(ProductNotFoundError):
        use_case.execute("inv-1", "aisle-1", "pos-1", "prod-unknown", 5)


def test_update_quantity_product_wrong_position_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    position = Position(
        id="pos-1", aisle_id="aisle-1", status=PositionStatus.DETECTED,
        confidence=0.9, needs_review=True, primary_evidence_id=None,
        created_at=now, updated_at=now,
    )
    product = ProductRecord(
        id="prod-1", position_id="other-pos", sku="X", description=None,
        detected_quantity=1, corrected_quantity=None, confidence=0.9,
        created_at=now, updated_at=now,
    )
    use_case = UpdateProductQuantityUseCase(
        inventory_repo=StubInventoryRepo(inv),
        aisle_repo=StubAisleRepo(aisle),
        position_repo=StubPositionRepo(position),
        product_record_repo=StubProductRepo(product),
        review_repo=StubReviewRepo(),
        clock=FixedClock(now),
    )
    with pytest.raises(ProductNotFoundError):
        use_case.execute("inv-1", "aisle-1", "pos-1", "prod-1", 5)
