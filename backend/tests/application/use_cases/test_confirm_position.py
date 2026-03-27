"""Tests for ConfirmPositionUseCase — Épica 8."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

import pytest

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    PositionDeletedError,
    PositionNotFoundError,
)
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.confirm_position import ConfirmPositionUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
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

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubAisleRepo:
    def __init__(self, aisle: Optional[Aisle] = None) -> None:
        self._store = {} if aisle is None else {aisle.id: aisle}

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code:
                return a
        return None


class StubPositionRepo:
    def __init__(self, position: Optional[Position] = None) -> None:
        self._store = {} if position is None else {position.id: position}

    def get_by_id(self, position_id: str) -> Optional[Position]:
        return self._store.get(position_id)

    def save(self, position: Position) -> None:
        self._store[position.id] = position

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        want = set(aisle_ids)
        return [p for p in self._store.values() if p.aisle_id in want]


class StubReviewRepo:
    def __init__(self) -> None:
        self._actions: list[ReviewAction] = []

    def save(self, review: ReviewAction) -> None:
        self._actions.append(review)

    def list_by_position(self, position_id: str) -> Sequence[ReviewAction]:
        return [a for a in self._actions if a.position_id == position_id]


def _aisle_review_sync(
    inv_repo: StubInventoryRepo,
    aisle_repo: StubAisleRepo,
    position_repo: StubPositionRepo,
    clock: FixedClock,
) -> AisleReviewLifecycleSync:
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    return AisleReviewLifecycleSync(aisle_repo, position_repo, clock, reconciler)


def test_confirm_position_sets_reviewed_and_creates_audit() -> None:
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
    inv_repo = StubInventoryRepo(inv)
    aisle_repo = StubAisleRepo(aisle)
    position_repo = StubPositionRepo(position)
    review_repo = StubReviewRepo()
    clock = FixedClock(now)

    use_case = ConfirmPositionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=_aisle_review_sync(inv_repo, aisle_repo, position_repo, clock),
    )
    use_case.execute("inv-1", "aisle-1", "pos-1")

    updated = position_repo.get_by_id("pos-1")
    assert updated is not None
    assert updated.status == PositionStatus.REVIEWED
    actions = review_repo.list_by_position("pos-1")
    assert len(actions) == 1
    assert actions[0].action_type == ReviewActionType.CONFIRM
    assert actions[0].before_json.get("status") == "detected"
    assert actions[0].after_json.get("status") == "reviewed"


def test_confirm_position_inventory_not_found_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo(None)
    aisle_repo = StubAisleRepo()
    position_repo = StubPositionRepo()
    review_repo = StubReviewRepo()
    use_case = ConfirmPositionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=FixedClock(now),
        aisle_review_sync=_aisle_review_sync(inv_repo, aisle_repo, position_repo, FixedClock(now)),
    )
    with pytest.raises(InventoryNotFoundError):
        use_case.execute("inv-1", "aisle-1", "pos-1")


def test_confirm_position_aisle_not_found_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo(inv)
    aisle_repo = StubAisleRepo(None)
    position_repo = StubPositionRepo()
    review_repo = StubReviewRepo()
    use_case = ConfirmPositionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=FixedClock(now),
        aisle_review_sync=_aisle_review_sync(inv_repo, aisle_repo, position_repo, FixedClock(now)),
    )
    with pytest.raises(AisleNotFoundError):
        use_case.execute("inv-1", "aisle-1", "pos-1")


def test_confirm_position_position_not_found_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    inv_repo = StubInventoryRepo(inv)
    aisle_repo = StubAisleRepo(aisle)
    position_repo = StubPositionRepo(None)
    review_repo = StubReviewRepo()
    use_case = ConfirmPositionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=FixedClock(now),
        aisle_review_sync=_aisle_review_sync(inv_repo, aisle_repo, position_repo, FixedClock(now)),
    )
    with pytest.raises(PositionNotFoundError):
        use_case.execute("inv-1", "aisle-1", "pos-1")


def test_confirm_position_position_wrong_aisle_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    position = Position(
        id="pos-1",
        aisle_id="other-aisle",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
    )
    inv_repo = StubInventoryRepo(inv)
    aisle_repo = StubAisleRepo(aisle)
    position_repo = StubPositionRepo(position)
    review_repo = StubReviewRepo()
    use_case = ConfirmPositionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=FixedClock(now),
        aisle_review_sync=_aisle_review_sync(inv_repo, aisle_repo, position_repo, FixedClock(now)),
    )
    with pytest.raises(PositionNotFoundError):
        use_case.execute("inv-1", "aisle-1", "pos-1")


def test_confirm_position_already_deleted_raises() -> None:
    """Confirm on an already-deleted position raises PositionDeletedError."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    position = Position(
        id="pos-1",
        aisle_id="aisle-1",
        status=PositionStatus.DELETED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
    )
    inv_repo = StubInventoryRepo(inv)
    aisle_repo = StubAisleRepo(aisle)
    position_repo = StubPositionRepo(position)
    review_repo = StubReviewRepo()
    use_case = ConfirmPositionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=FixedClock(now),
        aisle_review_sync=_aisle_review_sync(inv_repo, aisle_repo, position_repo, FixedClock(now)),
    )
    with pytest.raises(PositionDeletedError):
        use_case.execute("inv-1", "aisle-1", "pos-1")


def test_confirm_position_marks_aisle_completed_and_reconciles_inventory_when_review_done() -> None:
    """After clearing needs_review on all positions, aisle becomes completed and inventory rolls up."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.IN_REVIEW, now, now)
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.PROCESSED, now, now)
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
    inv_repo = StubInventoryRepo(inv)
    aisle_repo = StubAisleRepo(aisle)
    position_repo = StubPositionRepo(position)
    review_repo = StubReviewRepo()
    clock = FixedClock(now)
    sync = _aisle_review_sync(inv_repo, aisle_repo, position_repo, clock)
    use_case = ConfirmPositionUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=sync,
    )
    use_case.execute("inv-1", "aisle-1", "pos-1")

    assert aisle_repo.get_by_id("aisle-1") is not None
    assert aisle_repo.get_by_id("aisle-1").status == AisleStatus.COMPLETED
    assert inv_repo.get_by_id("inv-1") is not None
    assert inv_repo.get_by_id("inv-1").status == InventoryStatus.COMPLETED
