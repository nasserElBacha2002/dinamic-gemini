"""Unit tests: inventory status detect / repair / idempotency / post-commit recovery."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.services.inventory_status_reconciler import (
    InventoryStatusReconciler,
    InventoryStatusRepairOutcome,
)
from src.application.use_cases.inventories.backfill_inventory_statuses import (
    BackfillInventoryStatusesUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.derive_status_from_aisles import (
    REASON_AISLE_PROCESSED_OR_IN_REVIEW,
    REASON_AISLE_QUEUED_OR_PROCESSING,
    REASON_AISLE_SETUP_ACTIVITY,
    REASON_ALL_AISLES_COMPLETED,
    REASON_ANY_AISLE_FAILED,
    REASON_FALLBACK_DRAFT,
    REASON_NO_OPERATIONAL_AISLES,
    derive_inventory_status_with_reason,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _stack(*, max_attempts: int = 3, before_cas_hook=None):
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    clock = FixedClock(_NOW)
    reconciler = InventoryStatusReconciler(
        inv_repo,
        aisle_repo,
        clock,
        max_attempts=max_attempts,
        before_cas_hook=before_cas_hook,
    )
    return inv_repo, aisle_repo, reconciler


@pytest.mark.parametrize(
    ("aisles", "expected_status", "expected_reason"),
    [
        ((), InventoryStatus.DRAFT, REASON_NO_OPERATIONAL_AISLES),
        (
            (AisleStatus.FAILED,),
            InventoryStatus.FAILED,
            REASON_ANY_AISLE_FAILED,
        ),
        (
            (AisleStatus.QUEUED,),
            InventoryStatus.PROCESSING,
            REASON_AISLE_QUEUED_OR_PROCESSING,
        ),
        (
            (AisleStatus.PROCESSING,),
            InventoryStatus.PROCESSING,
            REASON_AISLE_QUEUED_OR_PROCESSING,
        ),
        (
            (AisleStatus.PROCESSED,),
            InventoryStatus.IN_REVIEW,
            REASON_AISLE_PROCESSED_OR_IN_REVIEW,
        ),
        (
            (AisleStatus.IN_REVIEW,),
            InventoryStatus.IN_REVIEW,
            REASON_AISLE_PROCESSED_OR_IN_REVIEW,
        ),
        (
            (AisleStatus.COMPLETED,),
            InventoryStatus.COMPLETED,
            REASON_ALL_AISLES_COMPLETED,
        ),
        (
            (AisleStatus.CREATED,),
            InventoryStatus.PROCESSING,
            REASON_AISLE_SETUP_ACTIVITY,
        ),
        (
            (AisleStatus.ASSETS_UPLOADED,),
            InventoryStatus.PROCESSING,
            REASON_AISLE_SETUP_ACTIVITY,
        ),
    ],
)
def test_reason_matrix_covers_all_codes(
    aisles: tuple[AisleStatus, ...],
    expected_status: InventoryStatus,
    expected_reason: str,
) -> None:
    entities = tuple(
        Aisle(f"a{i}", "inv", f"C{i}", status, _NOW, _NOW) for i, status in enumerate(aisles)
    )
    d = derive_inventory_status_with_reason(entities)
    assert d.status == expected_status
    assert d.reason == expected_reason


def test_fallback_draft_reason_for_unexpected_aisle_status() -> None:
    class _UnexpectedAisle:
        status = object()

    d = derive_inventory_status_with_reason((_UnexpectedAisle(),))  # type: ignore[arg-type]
    assert d.status == InventoryStatus.DRAFT
    assert d.reason == REASON_FALLBACK_DRAFT


def test_detect_reports_drift_without_write() -> None:
    inv_repo, aisle_repo, reconciler = _stack()
    inv_repo.save(Inventory("inv-1", "X", InventoryStatus.DRAFT, _NOW, _NOW))
    aisle_repo.save(Aisle("a1", "inv-1", "A", AisleStatus.COMPLETED, _NOW, _NOW))
    updated_at_before = inv_repo.get_by_id("inv-1").updated_at

    drift = reconciler.detect("inv-1")
    assert drift is not None
    assert drift.stored_status == InventoryStatus.DRAFT.value
    assert drift.expected_status == InventoryStatus.COMPLETED.value
    assert drift.reason == REASON_ALL_AISLES_COMPLETED
    assert inv_repo.get_by_id("inv-1").status == InventoryStatus.DRAFT
    assert inv_repo.get_by_id("inv-1").updated_at == updated_at_before


def test_repair_idempotent_zero_writes_on_second_call() -> None:
    inv_repo, aisle_repo, reconciler = _stack()
    inv_repo.save(Inventory("inv-2", "X", InventoryStatus.DRAFT, _NOW, _NOW))
    aisle_repo.save(Aisle("a1", "inv-2", "A", AisleStatus.PROCESSED, _NOW, _NOW))

    first = reconciler.repair("inv-2")
    assert first.outcome == InventoryStatusRepairOutcome.REPAIRED
    assert inv_repo.get_by_id("inv-2").status == InventoryStatus.IN_REVIEW
    stamp = inv_repo.get_by_id("inv-2").updated_at

    second = reconciler.repair("inv-2")
    assert second.outcome == InventoryStatusRepairOutcome.CONSISTENT
    assert inv_repo.get_by_id("inv-2").updated_at == stamp
    assert reconciler.reconcile("inv-2") is False


def test_reconcile_false_when_consistent() -> None:
    inv_repo, aisle_repo, reconciler = _stack()
    inv_repo.save(
        Inventory("inv-3", "X", InventoryStatus.COMPLETED, _NOW, _NOW, completed_at=_NOW)
    )
    aisle_repo.save(Aisle("a1", "inv-3", "A", AisleStatus.COMPLETED, _NOW, _NOW))
    assert reconciler.detect("inv-3") is None
    assert reconciler.reconcile("inv-3") is False


def test_post_commit_reconcile_failure_then_retry_repairs() -> None:
    """Primary aisle change committed; reconciler fails once; later repair converges."""
    inv_repo, aisle_repo, reconciler = _stack()
    inv_repo.save(Inventory("inv-4", "X", InventoryStatus.DRAFT, _NOW, _NOW))
    aisle = Aisle("a1", "inv-4", "A", AisleStatus.CREATED, _NOW, _NOW)
    aisle_repo.save(aisle)

    aisle.mark_processed(_NOW)
    aisle_repo.save(aisle)
    assert inv_repo.get_by_id("inv-4").status == InventoryStatus.DRAFT
    assert reconciler.detect("inv-4") is not None

    repaired = reconciler.repair("inv-4")
    assert repaired.outcome == InventoryStatusRepairOutcome.REPAIRED
    assert inv_repo.get_by_id("inv-4").status == InventoryStatus.IN_REVIEW
    assert reconciler.detect("inv-4") is None


def test_backfill_detect_only_does_not_write() -> None:
    inv_repo, aisle_repo, reconciler = _stack()
    inv_repo.save(Inventory("inv-5", "X", InventoryStatus.DRAFT, _NOW, _NOW))
    aisle_repo.save(Aisle("a1", "inv-5", "A", AisleStatus.COMPLETED, _NOW, _NOW))
    result = BackfillInventoryStatusesUseCase(inv_repo, reconciler).execute(detect_only=True)
    assert result.inventories_scanned == 1
    assert result.inventories_updated == 0
    assert result.inventories_drifted == 1
    assert inv_repo.get_by_id("inv-5").status == InventoryStatus.DRAFT


def test_cas_miss_does_not_overwrite_concurrent_status() -> None:
    inv_repo, aisle_repo, reconciler = _stack()
    inv_repo.save(Inventory("inv-6", "X", InventoryStatus.DRAFT, _NOW, _NOW))
    aisle_repo.save(Aisle("a1", "inv-6", "A", AisleStatus.COMPLETED, _NOW, _NOW))

    assert inv_repo.compare_and_set_status(
        "inv-6",
        expected_current=InventoryStatus.DRAFT,
        new_status=InventoryStatus.COMPLETED,
        updated_at=_NOW,
        completed_at=_NOW,
    )
    assert reconciler.detect("inv-6") is None


def test_repair_sets_and_clears_completed_at() -> None:
    inv_repo, aisle_repo, reconciler = _stack()
    inv_repo.save(Inventory("inv-7", "X", InventoryStatus.DRAFT, _NOW, _NOW))
    aisle_repo.save(Aisle("a1", "inv-7", "A", AisleStatus.COMPLETED, _NOW, _NOW))

    assert reconciler.repair("inv-7").outcome == InventoryStatusRepairOutcome.REPAIRED
    inv = inv_repo.get_by_id("inv-7")
    assert inv.status == InventoryStatus.COMPLETED
    assert inv.completed_at == _NOW

    aisle = aisle_repo.get_by_id("a1")
    assert aisle is not None
    aisle.status = AisleStatus.PROCESSING
    aisle_repo.save(aisle)

    assert reconciler.repair("inv-7").outcome == InventoryStatusRepairOutcome.REPAIRED
    inv2 = inv_repo.get_by_id("inv-7")
    assert inv2.status == InventoryStatus.PROCESSING
    assert inv2.completed_at is None


def test_retry_exhausted_when_source_keeps_changing() -> None:
    inv_repo, aisle_repo, _ = _stack()
    inv_repo.save(Inventory("inv-8", "X", InventoryStatus.DRAFT, _NOW, _NOW))
    aisle_repo.save(Aisle("a1", "inv-8", "A", AisleStatus.COMPLETED, _NOW, _NOW))

    flip = {"n": 0}

    def mutate_before_cas() -> None:
        flip["n"] += 1
        aisle = aisle_repo.get_by_id("a1")
        assert aisle is not None
        # Alternate PROCESSING <-> FAILED so verify-after-write always disagrees
        # with the status just written from the pre-hook snapshot.
        aisle.status = AisleStatus.PROCESSING if flip["n"] % 2 else AisleStatus.FAILED
        aisle_repo.save(aisle)

    reconciler = InventoryStatusReconciler(
        inv_repo,
        aisle_repo,
        FixedClock(_NOW),
        max_attempts=2,
        before_cas_hook=mutate_before_cas,
    )
    result = reconciler.repair("inv-8")
    assert result.outcome == InventoryStatusRepairOutcome.RETRY_EXHAUSTED
    assert result.attempts == 2
    # Still repairable once the source stops changing.
    aisle = aisle_repo.get_by_id("a1")
    assert aisle is not None
    aisle.status = AisleStatus.FAILED
    aisle_repo.save(aisle)
    later = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(_NOW)).repair("inv-8")
    assert later.outcome == InventoryStatusRepairOutcome.REPAIRED
    assert inv_repo.get_by_id("inv-8").status == InventoryStatus.FAILED
    assert inv_repo.get_by_id("inv-8").completed_at is None
    assert InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(_NOW)).detect("inv-8") is None
