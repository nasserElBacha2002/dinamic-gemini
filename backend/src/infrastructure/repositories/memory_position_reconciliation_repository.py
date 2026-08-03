"""Thread-safe in-memory Phase 4 reconciliation repository."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock

from src.domain.position_reconciliation.entities import (
    AssignmentStatus,
    PositionReconciliation,
    ProductPositionAssignment,
    ReconciliationStatus,
)


class MemoryPositionReconciliationRepository:
    def __init__(self) -> None:
        self._reconciliations: dict[str, PositionReconciliation] = {}
        self._assignments: dict[str, ProductPositionAssignment] = {}
        self._lock = RLock()

    def get_active_by_job(self, job_id: str) -> PositionReconciliation | None:
        with self._lock:
            return next(
                (
                    row
                    for row in self._reconciliations.values()
                    if row.job_id == job_id and row.is_active
                ),
                None,
            )

    def get_by_id(self, reconciliation_id: str) -> PositionReconciliation | None:
        with self._lock:
            return self._reconciliations.get(reconciliation_id)

    def mark_stale(self, job_id: str) -> PositionReconciliation | None:
        with self._lock:
            row = self.get_active_by_job(job_id)
            if row is None:
                return None
            row.status = ReconciliationStatus.STALE
            row.updated_at = datetime.now(timezone.utc)
            return row

    def begin_or_get_running(
        self, reconciliation: PositionReconciliation
    ) -> PositionReconciliation:
        with self._lock:
            active = self.get_active_by_job(reconciliation.job_id)
            if active is not None and active.status in {
                ReconciliationStatus.RUNNING,
                ReconciliationStatus.COMPLETED,
            }:
                return active
            self._reconciliations[reconciliation.id] = reconciliation
            return reconciliation

    def persist_revision_atomically(
        self,
        reconciliation: PositionReconciliation,
        assignments: Sequence[ProductPositionAssignment],
        previous_active_id: str | None,
    ) -> PositionReconciliation:
        with self._lock:
            now = reconciliation.updated_at
            old_reconciliations = dict(self._reconciliations)
            old_assignments = dict(self._assignments)
            try:
                for recon in self._reconciliations.values():
                    if recon.job_id == reconciliation.job_id and recon.is_active:
                        recon.is_active = False
                        recon.superseded_at = now
                        recon.updated_at = now
                for assignment_id, assignment_row in tuple(self._assignments.items()):
                    if assignment_row.job_id == reconciliation.job_id and assignment_row.is_active:
                        self._assignments[assignment_id] = replace(
                            assignment_row, is_active=False, superseded_at=now, updated_at=now
                        )
                reconciliation.is_active = True
                self._reconciliations[reconciliation.id] = reconciliation
                for assignment in assignments:
                    self._assignments[assignment.id] = assignment
            except Exception:
                self._reconciliations = old_reconciliations
                self._assignments = old_assignments
                raise
            return reconciliation

    def list_active_assignments(self, job_id: str) -> list[ProductPositionAssignment]:
        with self._lock:
            rows = [
                row for row in self._assignments.values() if row.job_id == job_id and row.is_active
            ]
            return sorted(
                rows,
                key=lambda row: (
                    row.sequence_number is None,
                    row.sequence_number or 0,
                    row.result_id,
                ),
            )

    def list_unassigned(self, job_id: str) -> list[ProductPositionAssignment]:
        return [
            row
            for row in self.list_active_assignments(job_id)
            if row.assignment_status is not AssignmentStatus.ASSIGNED_AUTOMATIC
        ]
