"""
Tests for v3.0 domain entities (Documento técnico §7).

Validates state transitions and basic invariants for Inventory, Aisle, Position.
"""

from datetime import datetime

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus

# --- Inventory ---


def test_inventory_mark_processing_updates_status_and_updated_at() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0)
    inv = Inventory(
        id="inv1",
        name="Test",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    later = datetime(2025, 3, 6, 13, 0, 0)
    inv.mark_processing(later)
    assert inv.status == InventoryStatus.PROCESSING
    assert inv.updated_at == later


def test_inventory_mark_completed_sets_completed_at() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0)
    inv = Inventory(
        id="inv1",
        name="Test",
        status=InventoryStatus.IN_REVIEW,
        created_at=now,
        updated_at=now,
    )
    later = datetime(2025, 3, 6, 14, 0, 0)
    inv.mark_completed(later)
    assert inv.status == InventoryStatus.COMPLETED
    assert inv.completed_at == later
    assert inv.updated_at == later


def test_inventory_mark_failed() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0)
    inv = Inventory(
        id="inv1",
        name="Test",
        status=InventoryStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    inv.mark_failed(now)
    assert inv.status == InventoryStatus.FAILED


# --- Aisle ---


def test_aisle_mark_assets_uploaded() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0)
    aisle = Aisle(
        id="a1",
        inventory_id="inv1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    later = datetime(2025, 3, 6, 12, 5, 0)
    aisle.mark_assets_uploaded(later)
    assert aisle.status == AisleStatus.ASSETS_UPLOADED
    assert aisle.updated_at == later


def test_aisle_mark_failed_sets_error_fields() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0)
    aisle = Aisle(
        id="a1",
        inventory_id="inv1",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    later = datetime(2025, 3, 6, 12, 10, 0)
    aisle.mark_failed(
        later,
        error_code="PIPELINE_FAILED",
        error_message="Timeout",
        retryable=True,
    )
    assert aisle.status == AisleStatus.FAILED
    assert aisle.error_code == "PIPELINE_FAILED"
    assert aisle.error_message == "Timeout"
    assert aisle.retryable is True


# --- Position ---


def test_position_has_detected_status_by_default() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0)
    pos = Position(
        id="p1",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="e1",
        created_at=now,
        updated_at=now,
    )
    assert pos.status == PositionStatus.DETECTED
    assert pos.confidence == 0.9
    assert pos.needs_review is False
