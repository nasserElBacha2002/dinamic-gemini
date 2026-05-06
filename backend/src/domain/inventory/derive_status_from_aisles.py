"""
Derive aggregate inventory status from child aisles (v3).

Persisted `inventories.status` is reconciled from aisle state after operational events
so the inventory does not remain stuck in `draft` once work exists.

Priority (highest first): failed → active pipeline → review stage → all completed → setup → draft.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import InventoryStatus


def derive_inventory_status_from_aisles(aisles: Sequence[Aisle]) -> InventoryStatus:
    """
    Roll up aisle lifecycle into a single inventory status.

    - No aisles → draft
    - Any failed aisle → failed (surface operational problems)
    - Any queued/processing → processing
    - Any processed or in_review → in_review (results exist / review stage)
    - All aisles completed → completed
    - Only created / assets_uploaded → processing (inventory has operational activity)
    """
    if not aisles:
        return InventoryStatus.DRAFT

    statuses = [a.status for a in aisles]

    if any(s == AisleStatus.FAILED for s in statuses):
        return InventoryStatus.FAILED
    if any(s in (AisleStatus.QUEUED, AisleStatus.PROCESSING) for s in statuses):
        return InventoryStatus.PROCESSING
    if any(s in (AisleStatus.PROCESSED, AisleStatus.IN_REVIEW) for s in statuses):
        return InventoryStatus.IN_REVIEW
    if all(s == AisleStatus.COMPLETED for s in statuses):
        return InventoryStatus.COMPLETED
    if any(s in (AisleStatus.CREATED, AisleStatus.ASSETS_UPLOADED) for s in statuses):
        return InventoryStatus.PROCESSING

    return InventoryStatus.DRAFT
