"""
Derive aggregate inventory status from child aisles (v3).

Persisted ``inventories.status`` is a **fully derived projection** of active aisle
states (see ``InventoryStatusReconciler``). It is not an independent source of truth.

Priority (highest first): failed → active pipeline → review stage → all completed → setup → draft.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import InventoryStatus


@dataclass(frozen=True)
class InventoryStatusDerivation:
    """Result of pure status derivation (no I/O)."""

    status: InventoryStatus
    reason: str


# Stable reason codes for observability (detect / repair logs).
REASON_NO_OPERATIONAL_AISLES = "NO_OPERATIONAL_AISLES"
REASON_ANY_AISLE_FAILED = "ANY_AISLE_FAILED"
REASON_AISLE_QUEUED_OR_PROCESSING = "AISLE_QUEUED_OR_PROCESSING"
REASON_AISLE_PROCESSED_OR_IN_REVIEW = "AISLE_PROCESSED_OR_IN_REVIEW"
REASON_ALL_AISLES_COMPLETED = "ALL_AISLES_COMPLETED"
REASON_AISLE_SETUP_ACTIVITY = "AISLE_SETUP_ACTIVITY"
REASON_FALLBACK_DRAFT = "FALLBACK_DRAFT"


def derive_inventory_status_with_reason(
    aisles: Sequence[Aisle],
) -> InventoryStatusDerivation:
    """
    Roll up aisle lifecycle into a single inventory status + reason.

    - No aisles → draft
    - Any failed aisle → failed (surface operational problems)
    - Any queued/processing → processing
    - Any processed or in_review → in_review (results exist / review stage)
    - All aisles completed → completed
    - Only created / assets_uploaded → processing (inventory has operational activity)
    """
    if not aisles:
        return InventoryStatusDerivation(
            status=InventoryStatus.DRAFT,
            reason=REASON_NO_OPERATIONAL_AISLES,
        )

    statuses = [a.status for a in aisles]

    if any(s == AisleStatus.FAILED for s in statuses):
        return InventoryStatusDerivation(
            status=InventoryStatus.FAILED,
            reason=REASON_ANY_AISLE_FAILED,
        )
    if any(s in (AisleStatus.QUEUED, AisleStatus.PROCESSING) for s in statuses):
        return InventoryStatusDerivation(
            status=InventoryStatus.PROCESSING,
            reason=REASON_AISLE_QUEUED_OR_PROCESSING,
        )
    if any(s in (AisleStatus.PROCESSED, AisleStatus.IN_REVIEW) for s in statuses):
        return InventoryStatusDerivation(
            status=InventoryStatus.IN_REVIEW,
            reason=REASON_AISLE_PROCESSED_OR_IN_REVIEW,
        )
    if all(s == AisleStatus.COMPLETED for s in statuses):
        return InventoryStatusDerivation(
            status=InventoryStatus.COMPLETED,
            reason=REASON_ALL_AISLES_COMPLETED,
        )
    if any(s in (AisleStatus.CREATED, AisleStatus.ASSETS_UPLOADED) for s in statuses):
        return InventoryStatusDerivation(
            status=InventoryStatus.PROCESSING,
            reason=REASON_AISLE_SETUP_ACTIVITY,
        )

    return InventoryStatusDerivation(
        status=InventoryStatus.DRAFT,
        reason=REASON_FALLBACK_DRAFT,
    )


def derive_inventory_status_from_aisles(aisles: Sequence[Aisle]) -> InventoryStatus:
    """Backward-compatible status-only derivation."""
    return derive_inventory_status_with_reason(aisles).status
