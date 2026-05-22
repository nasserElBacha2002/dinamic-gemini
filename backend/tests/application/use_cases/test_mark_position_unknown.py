"""Tests for MarkPositionUnknownUseCase."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.errors import PositionNotFoundError
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.positions.mark_position_unknown import MarkPositionUnknownUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionReviewResolution, PositionStatus
from src.domain.reviews.entities import ReviewAction, ReviewActionType


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo:
    def __init__(self, inv: Inventory | None = None) -> None:
        self._store = {} if inv is None else {inv.id: inv}

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self._store.get(inventory_id)

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubAisleRepo:
    def __init__(self, aisle: Aisle | None = None) -> None:
        self._store = {} if aisle is None else {aisle.id: aisle}

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._store.get(aisle_id)

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]


class StubPositionRepo:
    def __init__(self, position: Position | None = None) -> None:
        self._store = {} if position is None else {position.id: position}

    def get_by_id(self, position_id: str) -> Position | None:
        return self._store.get(position_id)

    def save(self, position: Position) -> None:
        self._store[position.id] = position

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        wanted = set(aisle_ids)
        return [p for p in self._store.values() if p.aisle_id in wanted]


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


def test_mark_unknown_sets_terminal_resolution_and_creates_audit() -> None:
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
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

    use_case = MarkPositionUnknownUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=_aisle_review_sync(inv_repo, aisle_repo, position_repo, clock),
    )
    use_case.execute("inv-1", "aisle-1", "pos-1", None)

    updated = position_repo.get_by_id("pos-1")
    assert updated is not None
    assert updated.status == PositionStatus.REVIEWED
    assert updated.needs_review is False
    assert updated.review_resolution == PositionReviewResolution.UNKNOWN

    actions = review_repo.list_by_position("pos-1")
    assert len(actions) == 1
    assert actions[0].action_type == ReviewActionType.MARK_UNKNOWN
    assert actions[0].after_json["review_resolution"] == "unknown"


def test_mark_unknown_not_found_raises() -> None:
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "WH", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.CREATED, now, now)
    inv_repo = StubInventoryRepo(inv)
    aisle_repo = StubAisleRepo(aisle)
    position_repo = StubPositionRepo(None)
    clock = FixedClock(now)

    use_case = MarkPositionUnknownUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=StubReviewRepo(),
        clock=clock,
        aisle_review_sync=_aisle_review_sync(inv_repo, aisle_repo, position_repo, clock),
    )

    with pytest.raises(PositionNotFoundError):
        use_case.execute("inv-1", "aisle-1", "missing", None)
