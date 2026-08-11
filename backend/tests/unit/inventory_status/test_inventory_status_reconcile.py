"""Unit tests: inventory status detect / repair / idempotency / post-commit recovery."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.inventories.backfill_inventory_statuses import (
    BackfillInventoryStatusesUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.derive_status_from_aisles import (
    REASON_ALL_AISLES_COMPLETED,
    REASON_ANY_AISLE_FAILED,
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


def _stack():
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    clock = FixedClock(_NOW)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    return inv_repo, aisle_repo, reconciler


def test_derive_reasons_cover_priority_paths() -> None:
    aisle = Aisle("a1", "inv", "A", AisleStatus.FAILED, _NOW, _NOW)
    d = derive_inventory_status_with_reason((aisle,))
    assert d.status == InventoryStatus.FAILED
    assert d.reason == REASON_ANY_AISLE_FAILED

    done = Aisle("a2", "inv", "B", AisleStatus.COMPLETED, _NOW, _NOW)
    d2 = derive_inventory_status_with_reason((done,))
    assert d2.status == InventoryStatus.COMPLETED
    assert d2.reason == REASON_ALL_AISLES_COMPLETED


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
    assert first is not None
    assert inv_repo.get_by_id("inv-2").status == InventoryStatus.IN_REVIEW
    stamp = inv_repo.get_by_id("inv-2").updated_at

    second = reconciler.repair("inv-2")
    assert second is None
    assert inv_repo.get_by_id("inv-2").updated_at == stamp
    assert reconciler.reconcile("inv-2") is False


def test_reconcile_false_when_consistent() -> None:
    inv_repo, aisle_repo, reconciler = _stack()
    inv_repo.save(Inventory("inv-3", "X", InventoryStatus.COMPLETED, _NOW, _NOW))
    aisle_repo.save(Aisle("a1", "inv-3", "A", AisleStatus.COMPLETED, _NOW, _NOW))
    assert reconciler.detect("inv-3") is None
    assert reconciler.reconcile("inv-3") is False


def test_post_commit_reconcile_failure_then_retry_repairs() -> None:
    """Primary aisle change committed; reconciler fails once; later repair converges."""
    inv_repo, aisle_repo, reconciler = _stack()
    inv_repo.save(Inventory("inv-4", "X", InventoryStatus.DRAFT, _NOW, _NOW))
    aisle = Aisle("a1", "inv-4", "A", AisleStatus.CREATED, _NOW, _NOW)
    aisle_repo.save(aisle)

    # Simulate primary commit: aisle marked processed without successful reconcile.
    aisle.mark_processed(_NOW)
    aisle_repo.save(aisle)
    assert inv_repo.get_by_id("inv-4").status == InventoryStatus.DRAFT
    assert reconciler.detect("inv-4") is not None

    repaired = reconciler.repair("inv-4")
    assert repaired is not None
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

    # Another writer already moved status to the expected value.
    assert inv_repo.compare_and_set_status(
        "inv-6",
        expected_current=InventoryStatus.DRAFT,
        new_status=InventoryStatus.COMPLETED,
        updated_at=_NOW,
        completed_at=_NOW,
    )
    # Drift detect still sees consistent state.
    assert reconciler.detect("inv-6") is None
