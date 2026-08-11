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
    """Terminal outcomes of ``repair`` (never intermediate retry states)."""

    CONSISTENT = "consistent"
    REPAIRED = "repaired"
    NOT_FOUND = "not_found"
    RETRY_EXHAUSTED = "retry_exhausted"


class InventoryStatusConflictReason(str, Enum):
    """Last optimistic conflict observed before success or ``RETRY_EXHAUSTED``."""

    CAS_MISS = "cas_miss"
    SOURCE_CHANGED = "source_changed"


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
    last_conflict_reason: InventoryStatusConflictReason | None = None


class InventoryStatusReconciler:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        clock: Clock,
        *,
        max_attempts: int = MAX_RECONCILE_ATTEMPTS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._clock = clock
        self._max_attempts = max_attempts

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

        ``REPAIRED`` means the persisted status matched a fresh aisle snapshot at the
        verify-after-write verification point. An aisle mutation occurring after that
        verification may create new drift and is expected to trigger a subsequent
        reconciliation. This is optimistic concurrency without holding aisle locks.
        """
        started = time.perf_counter()
        last_conflict: InventoryStatusConflictReason | None = None
        last_drift: InventoryStatusDrift | None = None

        for attempt in range(1, self._max_attempts + 1):
            inv = self._inventory_repo.get_by_id(inventory_id)
            if inv is None:
                return InventoryStatusRepairResult(
                    outcome=InventoryStatusRepairOutcome.NOT_FOUND,
                    attempts=attempt,
                    last_conflict_reason=last_conflict,
                )

            scope = scope_from_aisles(self._aisle_repo.list_by_inventory(inventory_id))
            derivation = derive_inventory_status_with_reason(scope.operational_aisles)
            if derivation.status == inv.status:
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
                        last_conflict_reason=last_conflict,
                    )
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

            cas_ok = self._inventory_repo.compare_and_set_status(
                inventory_id,
                expected_current=stored,
                new_status=expected,
                updated_at=now,
                completed_at=completed_at,
            )
            if not cas_ok:
                last_conflict = InventoryStatusConflictReason.CAS_MISS
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
                    last_conflict_reason=last_conflict,
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
                    last_conflict_reason=last_conflict,
                )

            last_conflict = InventoryStatusConflictReason.SOURCE_CHANGED
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

        logger.warning(
            "status_reconcile entity_type=inventory entity_id=%s action=retry_exhausted "
            "last_conflict=%s attempts=%s",
            inventory_id,
            last_conflict.value if last_conflict else None,
            self._max_attempts,
        )
        return InventoryStatusRepairResult(
            outcome=InventoryStatusRepairOutcome.RETRY_EXHAUSTED,
            drift=last_drift,
            attempts=self._max_attempts,
            last_conflict_reason=last_conflict,
        )

    def reconcile(self, inventory_id: str) -> bool:
        """Backward-compatible wrapper: True only when an effective repair occurred.

        ``False`` means no write from this call — covering ``CONSISTENT``, ``NOT_FOUND``,
        and ``RETRY_EXHAUSTED``. Do **not** treat ``False`` as proof of consistency:
        exhaustion leaves detectable drift for a later ``repair`` / backfill.

        Callers that must guarantee convergence (or distinguish exhaustion) should call
        ``repair()`` and inspect ``InventoryStatusRepairResult.outcome``.
        """
        result = self.repair(inventory_id)
        if result.outcome == InventoryStatusRepairOutcome.RETRY_EXHAUSTED:
            logger.warning(
                "status_reconcile entity_type=inventory entity_id=%s "
                "action=retry_exhausted_via_reconcile_wrapper "
                "last_conflict=%s attempts=%s",
                inventory_id,
                result.last_conflict_reason.value if result.last_conflict_reason else None,
                result.attempts,
            )
        return result.outcome == InventoryStatusRepairOutcome.REPAIRED


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
