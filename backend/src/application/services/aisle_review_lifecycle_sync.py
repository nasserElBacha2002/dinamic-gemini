"""
Advance aisle lifecycle after manual review mutations (v3).

Pipeline leaves aisles in ``processed``; when operators clear ``needs_review`` on all
positions, the aisle becomes ``completed`` so aggregate inventory status can leave
``in_review``. Optionally moves ``processed`` → ``in_review`` while work remains.

Uses an EXISTS-style pending check when the position repository supports it, to avoid
loading every position inside a write transaction.
"""

from __future__ import annotations

import logging

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, PositionRepository
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.aisle.entities import AisleStatus

logger = logging.getLogger(__name__)


def _aisle_has_pending_review(position_repo: PositionRepository, aisle_id: str) -> bool:
    checker = getattr(position_repo, "aisle_has_needs_review", None)
    if callable(checker):
        return bool(checker(aisle_id))
    positions = list(position_repo.list_by_aisles([aisle_id]))
    return any(p.needs_review for p in positions)


class AisleReviewLifecycleSync:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        clock: Clock,
        status_reconciler: InventoryStatusReconciler,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._clock = clock
        self._status_reconciler = status_reconciler

    def after_review_mutation(self, inventory_id: str, aisle_id: str) -> None:
        """Persist aisle stage changes driven by position review state, then roll up inventory."""
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None or aisle.inventory_id != inventory_id:
            logger.warning(
                "AisleReviewLifecycleSync: skip; aisle=%s inventory=%s mismatch or missing",
                aisle_id,
                inventory_id,
            )
            return

        if aisle.status in (AisleStatus.PROCESSED, AisleStatus.IN_REVIEW):
            pending = _aisle_has_pending_review(self._position_repo, aisle_id)
            now = self._clock.now()
            changed = False
            if pending:
                if aisle.status == AisleStatus.PROCESSED:
                    aisle.mark_in_review(now)
                    changed = True
            elif aisle.status in (AisleStatus.PROCESSED, AisleStatus.IN_REVIEW):
                aisle.mark_completed(now)
                changed = True
            if changed:
                self._aisle_repo.save(aisle)

        # Inventory rollup is aisle-level (not a full position scan).
        self._status_reconciler.reconcile(inventory_id)
