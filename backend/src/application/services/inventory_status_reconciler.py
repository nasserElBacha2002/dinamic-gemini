"""
Reconcile persisted inventory.status from aisle aggregates (v3).

``inventories.status`` is a fully derived projection of active aisle states.
Detect and repair are separate so operators can observe drift without writing.

Called after aisle lifecycle changes so list/detail APIs stay aligned without
frontend overrides. Safe to retry after post-commit failures.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.inventory_aggregation_scope import scope_from_aisles
from src.domain.inventory.derive_status_from_aisles import derive_inventory_status_with_reason
from src.domain.inventory.entities import Inventory, InventoryStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InventoryStatusDrift:
    """Detected mismatch between persisted inventory status and aisle-derived expectation."""

    entity_id: str
    stored_status: str
    expected_status: str
    reason: str


class InventoryStatusReconciler:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        clock: Clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._clock = clock

    def detect(self, inventory_id: str, *, log: bool = True) -> InventoryStatusDrift | None:
        """Return drift when stored status differs from aisle-derived expectation.

        Does not write. Inactive aisles are ignored (same scope as repair).
        """
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            return None
        scope = scope_from_aisles(self._aisle_repo.list_by_inventory(inventory_id))
        derivation = derive_inventory_status_with_reason(scope.operational_aisles)
        if derivation.status == inv.status:
            if log:
                logger.debug(
                    "status_reconcile entity_type=inventory entity_id=%s action=consistent "
                    "stored_status=%s reason=%s",
                    inventory_id,
                    inv.status.value,
                    derivation.reason,
                )
            return None
        drift = InventoryStatusDrift(
            entity_id=inventory_id,
            stored_status=inv.status.value,
            expected_status=derivation.status.value,
            reason=derivation.reason,
        )
        if log:
            logger.warning(
                "status_reconcile entity_type=inventory entity_id=%s action=detected "
                "stored_status=%s expected_status=%s reason=%s",
                drift.entity_id,
                drift.stored_status,
                drift.expected_status,
                drift.reason,
            )
        return drift

    def repair(self, inventory_id: str) -> InventoryStatusDrift | None:
        """Persist expected status when drifted. Returns the repaired drift, or None if consistent.

        Idempotent: second call with no intervening aisle changes performs zero writes.
        Uses compare-and-set when the repository supports it to avoid clobbering a concurrent
        status transition that already moved the row away from ``stored_status``.
        """
        started = time.perf_counter()
        drift = self.detect(inventory_id, log=True)
        if drift is None:
            return None

        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            return None

        # Concurrent repair already converged.
        if inv.status.value == drift.expected_status:
            return None

        # Concurrent domain transition: re-detect once from fresh aisle snapshot.
        if inv.status.value != drift.stored_status:
            logger.info(
                "status_reconcile entity_type=inventory entity_id=%s action=concurrent_reread "
                "stored_was=%s stored_now=%s",
                inventory_id,
                drift.stored_status,
                inv.status.value,
            )
            drift = self.detect(inventory_id, log=False)
            if drift is None:
                return None
            inv = self._inventory_repo.get_by_id(inventory_id)
            if inv is None or inv.status.value == drift.expected_status:
                return None

        now = self._clock.now()
        expected = InventoryStatus(drift.expected_status)
        completed_at = inv.completed_at
        if expected == InventoryStatus.COMPLETED:
            if inv.status != InventoryStatus.COMPLETED and completed_at is None:
                completed_at = now
        elif inv.status == InventoryStatus.COMPLETED:
            completed_at = None

        cas = getattr(self._inventory_repo, "compare_and_set_status", None)
        if callable(cas):
            updated = cas(
                inventory_id,
                expected_current=InventoryStatus(drift.stored_status),
                new_status=expected,
                updated_at=now,
                completed_at=completed_at,
            )
            if not updated:
                # Lost the race — leave for a later detect/repair; do not overwrite blindly.
                logger.info(
                    "status_reconcile entity_type=inventory entity_id=%s action=cas_miss "
                    "stored_status=%s expected_status=%s reason=%s",
                    inventory_id,
                    drift.stored_status,
                    drift.expected_status,
                    drift.reason,
                )
                return None
        else:
            _apply_status_transition(inv, expected, now)
            self._inventory_repo.save(inv)

        duration_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "status_reconcile entity_type=inventory entity_id=%s action=repaired "
            "stored_status=%s expected_status=%s reason=%s duration_ms=%.2f",
            drift.entity_id,
            drift.stored_status,
            drift.expected_status,
            drift.reason,
            duration_ms,
        )
        return drift

    def reconcile(self, inventory_id: str) -> bool:
        """Recompute status from active aisles and persist if drifted. Returns True if repaired.

        Inactive aisles are ignored so a soft-deactivated failed/pending aisle cannot keep the
        inventory stuck. With no active aisles, derivation yields DRAFT.
        """
        return self.repair(inventory_id) is not None


def _apply_status_transition(inv: Inventory, new_status: InventoryStatus, now: datetime) -> None:
    prev = inv.status
    inv.status = new_status
    inv.updated_at = now
    if new_status == InventoryStatus.COMPLETED:
        if prev != InventoryStatus.COMPLETED and inv.completed_at is None:
            inv.completed_at = now
    elif prev == InventoryStatus.COMPLETED:
        inv.completed_at = None
