"""Roll-up rules: inventory status from child aisles."""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.derive_status_from_aisles import derive_inventory_status_from_aisles
from src.domain.inventory.entities import InventoryStatus

_NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _aisle(status: AisleStatus, code: str = "A1") -> Aisle:
    return Aisle("a-x", "inv-1", code, status, _NOW, _NOW)


def test_no_aisles_is_draft() -> None:
    assert derive_inventory_status_from_aisles(()) == InventoryStatus.DRAFT


def test_any_failed_wins() -> None:
    aisles = (_aisle(AisleStatus.COMPLETED, "C"), _aisle(AisleStatus.FAILED, "F"))
    assert derive_inventory_status_from_aisles(aisles) == InventoryStatus.FAILED


def test_queued_or_processing() -> None:
    aisles = (_aisle(AisleStatus.CREATED), _aisle(AisleStatus.QUEUED))
    assert derive_inventory_status_from_aisles(aisles) == InventoryStatus.PROCESSING


def test_processed_implies_in_review_for_inventory() -> None:
    assert derive_inventory_status_from_aisles((_aisle(AisleStatus.PROCESSED),)) == InventoryStatus.IN_REVIEW


def test_all_completed() -> None:
    aisles = (_aisle(AisleStatus.COMPLETED, "1"), _aisle(AisleStatus.COMPLETED, "2"))
    assert derive_inventory_status_from_aisles(aisles) == InventoryStatus.COMPLETED


def test_only_created_or_assets_uploaded_is_processing() -> None:
    assert derive_inventory_status_from_aisles((_aisle(AisleStatus.CREATED),)) == InventoryStatus.PROCESSING
    assert (
        derive_inventory_status_from_aisles((_aisle(AisleStatus.ASSETS_UPLOADED),))
        == InventoryStatus.PROCESSING
    )
