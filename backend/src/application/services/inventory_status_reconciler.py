"""
Reconcile persisted inventory.status from aisle aggregates (v3).

SOURCE OF TRUTH: active aisle states.
DERIVED STATE: inventory.status.

Detect and repair are separate. Repair uses optimistic CAS on the inventory row
plus verify-after-write against a fresh aisle snapshot (bounded retries) so a
concurrent aisle mutation cannot leave COMPLETED (or any wrong rollup) sticky.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.inventory_aggregation_scope import scope_from_aisles
from src.domain.inventory.derive_status_from_aisles import derive_inventory_status_with_reason
from src.domain.inventory.entities import InventoryStatus

logger = logging.getLogger(__name__)

# Bounded optimistic attempts (CAS miss or aisle source changed after write).
MAX_RECONCILE_ATTEMPTS = 3


class InventoryStatusRepairOutcome(str, Enum):
    CONSISTENT = "consistent"
    REPAIRED = "repaired"
    NOT_FOUND = "not_found"
    CAS_MISS = "cas_miss"
    SOURCE_CHANGED = "source_changed"
    RETRY_EXHAUSTED = "retry_exhausted"


@dataclass(frozen=True)
class InventoryStatusDrift:
    """Detected mismatch between persisted inventory status and aisle-derived expectation."""

    entity_id: str
    stored_status: str
    expected_status: str
    reason: str


@dataclass(frozen=True)
class InventoryStatusRepairResult:
    """Typed result of ``repair`` (never overloads ``None`` for multiple meanings)."""

    outcome: InventoryStatusRepairOutcome
    drift: InventoryStatusDrift | None = None
    attempts: int = 0


class InventoryStatusReconciler:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        clock: Clock,
        *,
        max_attempts: int = MAX_RECONCILE_ATTEMPTS,
        before_cas_hook: Callable[[], None] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._clock = clock
        self._max_attempts = max_attempts
        # Test-only hook: invoked after derive, immediately before CAS (deterministic races).
        self._before_cas_hook = before_cas_hook

    def detect(self, inventory_id: str, *, log: bool = True) -> InventoryStatusDrift | None:
        """Return drift when stored status differs from aisle-derived expectation (read-only)."""
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

    def repair(self, inventory_id: str) -> InventoryStatusRepairResult:
        """Idempotent repair with CAS + verify-after-write (bounded retries).

        After a successful ``REPAIRED`` outcome, ``inventory.status`` matches
        ``derive(current active aisles)`` unless aisles mutate after this call returns.
        """
        started = time.perf_counter()
        last_outcome = InventoryStatusRepairOutcome.CONSISTENT
        last_drift: InventoryStatusDrift | None = None

        for attempt in range(1, self._max_attempts + 1):
            inv = self._inventory_repo.get_by_id(inventory_id)
            if inv is None:
                return InventoryStatusRepairResult(
                    outcome=InventoryStatusRepairOutcome.NOT_FOUND,
                    attempts=attempt,
                )

            scope = scope_from_aisles(self._aisle_repo.list_by_inventory(inventory_id))
            derivation = derive_inventory_status_with_reason(scope.operational_aisles)
            if derivation.status == inv.status:
                # Also ensure completed_at consistency for COMPLETED / non-COMPLETED.
                if not _completed_at_needs_fix(inv.status, inv.completed_at):
                    logger.debug(
                        "status_reconcile entity_type=inventory entity_id=%s action=consistent "
                        "stored_status=%s reason=%s attempt=%s",
                        inventory_id,
                        inv.status.value,
                        derivation.reason,
                        attempt,
                    )
                    return InventoryStatusRepairResult(
                        outcome=InventoryStatusRepairOutcome.CONSISTENT,
                        attempts=attempt,
                    )
                # Status matches but completed_at is wrong — still repair via CAS.
                expected = derivation.status
                stored = inv.status
                reason = derivation.reason
            else:
                expected = derivation.status
                stored = inv.status
                reason = derivation.reason
                last_drift = InventoryStatusDrift(
                    entity_id=inventory_id,
                    stored_status=stored.value,
                    expected_status=expected.value,
                    reason=reason,
                )
                logger.warning(
                    "status_reconcile entity_type=inventory entity_id=%s action=detected "
                    "stored_status=%s expected_status=%s reason=%s attempt=%s",
                    inventory_id,
                    stored.value,
                    expected.value,
                    reason,
                    attempt,
                )

            now = self._clock.now()
            completed_at = _completed_at_for_transition(stored, expected, inv.completed_at, now)

            if self._before_cas_hook is not None:
                self._before_cas_hook()

            cas_ok = self._inventory_repo.compare_and_set_status(
                inventory_id,
                expected_current=stored,
                new_status=expected,
                updated_at=now,
                completed_at=completed_at,
            )
            if not cas_ok:
                last_outcome = InventoryStatusRepairOutcome.CAS_MISS
                logger.info(
                    "status_reconcile entity_type=inventory entity_id=%s action=cas_miss "
                    "stored_status=%s expected_status=%s reason=%s attempt=%s",
                    inventory_id,
                    stored.value,
                    expected.value,
                    reason,
                    attempt,
                )
                continue

            # Verify-after-write: aisle source may have changed during the CAS window.
            scope_after = scope_from_aisles(self._aisle_repo.list_by_inventory(inventory_id))
            expected_after = derive_inventory_status_with_reason(scope_after.operational_aisles)
            persisted = self._inventory_repo.get_by_id(inventory_id)
            if persisted is None:
                return InventoryStatusRepairResult(
                    outcome=InventoryStatusRepairOutcome.NOT_FOUND,
                    attempts=attempt,
                )

            if (
                persisted.status == expected_after.status
                and not _completed_at_needs_fix(persisted.status, persisted.completed_at)
            ):
                duration_ms = (time.perf_counter() - started) * 1000.0
                drift = InventoryStatusDrift(
                    entity_id=inventory_id,
                    stored_status=stored.value,
                    expected_status=expected.value,
                    reason=reason,
                )
                logger.info(
                    "status_reconcile entity_type=inventory entity_id=%s action=repaired "
                    "stored_status=%s expected_status=%s reason=%s attempt=%s duration_ms=%.2f",
                    inventory_id,
                    stored.value,
                    expected.value,
                    reason,
                    attempt,
                    duration_ms,
                )
                return InventoryStatusRepairResult(
                    outcome=InventoryStatusRepairOutcome.REPAIRED,
                    drift=drift,
                    attempts=attempt,
                )

            last_outcome = InventoryStatusRepairOutcome.SOURCE_CHANGED
            last_drift = InventoryStatusDrift(
                entity_id=inventory_id,
                stored_status=persisted.status.value,
                expected_status=expected_after.status.value,
                reason=expected_after.reason,
            )
            logger.info(
                "status_reconcile entity_type=inventory entity_id=%s action=source_changed "
                "persisted_status=%s expected_after=%s reason=%s attempt=%s",
                inventory_id,
                persisted.status.value,
                expected_after.status.value,
                expected_after.reason,
                attempt,
            )
            # Loop retries to converge on the new aisle snapshot.

        logger.warning(
            "status_reconcile entity_type=inventory entity_id=%s action=retry_exhausted "
            "last_outcome=%s attempts=%s",
            inventory_id,
            last_outcome.value,
            self._max_attempts,
        )
        return InventoryStatusRepairResult(
            outcome=InventoryStatusRepairOutcome.RETRY_EXHAUSTED,
            drift=last_drift,
            attempts=self._max_attempts,
        )

    def reconcile(self, inventory_id: str) -> bool:
        """Backward-compatible wrapper: True only when an effective repair occurred.

        ``False`` covers consistent, not-found, cas_miss (exhausted), source_changed
        (exhausted), and retry_exhausted — callers that need detail should use ``repair``.
        """
        return self.repair(inventory_id).outcome == InventoryStatusRepairOutcome.REPAIRED


def _completed_at_for_transition(
    previous: InventoryStatus,
    new_status: InventoryStatus,
    current_completed_at: datetime | None,
    now: datetime,
) -> datetime | None:
    if new_status == InventoryStatus.COMPLETED:
        if previous != InventoryStatus.COMPLETED and current_completed_at is None:
            return now
        return current_completed_at if current_completed_at is not None else now
    return None


def _completed_at_needs_fix(
    status: InventoryStatus, completed_at: datetime | None
) -> bool:
    if status == InventoryStatus.COMPLETED:
        return completed_at is None
    return completed_at is not None
