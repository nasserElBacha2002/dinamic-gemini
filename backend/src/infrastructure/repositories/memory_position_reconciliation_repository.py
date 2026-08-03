"""Thread-safe in-memory Phase 4 reconciliation repository."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from threading import RLock

from src.application.errors import (
    PositionReconciliationConcurrentUpdateError,
    PositionReconciliationInputChangedError,
)
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

    def get_published_by_job(self, job_id: str) -> PositionReconciliation | None:
        with self._lock:
            return next(
                (
                    row
                    for row in self._reconciliations.values()
                    if row.job_id == job_id
                    and row.is_active
                    and row.status is ReconciliationStatus.COMPLETED
                ),
                None,
            )

    def get_active_by_job(self, job_id: str) -> PositionReconciliation | None:
        return self.get_published_by_job(job_id)

    def get_last_attempt_by_job(self, job_id: str) -> PositionReconciliation | None:
        with self._lock:
            rows = [row for row in self._reconciliations.values() if row.job_id == job_id]
            return max(rows, key=lambda row: (row.created_at, row.id), default=None)

    def get_by_id(self, reconciliation_id: str) -> PositionReconciliation | None:
        with self._lock:
            return self._reconciliations.get(reconciliation_id)

    def mark_stale(self, job_id: str) -> PositionReconciliation | None:
        """Deprecated: publication remains active until a replacement is published."""
        with self._lock:
            return self.get_published_by_job(job_id)

    def begin_or_get_running(
        self, reconciliation: PositionReconciliation
    ) -> PositionReconciliation:
        with self._lock:
            active_attempt = next(
                (
                    row
                    for row in self._reconciliations.values()
                    if row.job_id == reconciliation.job_id and row.is_active
                ),
                None,
            )
            if (
                active_attempt is not None
                and active_attempt.status is not ReconciliationStatus.COMPLETED
            ):
                active_attempt.is_active = False
                active_attempt.superseded_at = reconciliation.started_at
                active_attempt.updated_at = reconciliation.started_at
            published = self.get_published_by_job(reconciliation.job_id)
            if published is not None and published.input_fingerprint == reconciliation.input_fingerprint:
                return published
            running = next(
                (
                    row
                    for row in self._reconciliations.values()
                    if row.job_id == reconciliation.job_id
                    and row.status is ReconciliationStatus.RUNNING
                    and row.input_fingerprint == reconciliation.input_fingerprint
                ),
                None,
            )
            if running is not None:
                return running
            reconciliation.is_active = False
            self._reconciliations[reconciliation.id] = reconciliation
            return reconciliation

    def record_failed_attempt(
        self, attempt: PositionReconciliation
    ) -> PositionReconciliation:
        with self._lock:
            attempt.status = ReconciliationStatus.FAILED
            attempt.is_active = False
            self._reconciliations[attempt.id] = attempt
            return attempt

    def publish_completed_revision_atomically(
        self,
        reconciliation: PositionReconciliation,
        assignments: Sequence[ProductPositionAssignment],
        previous_active_id: str | None,
        expected_input_fingerprint: str,
    ) -> PositionReconciliation:
        with self._lock:
            if reconciliation.input_fingerprint != expected_input_fingerprint:
                raise PositionReconciliationInputChangedError(
                    "Reconciliation fingerprint changed before publication"
                )
            active = self.get_published_by_job(reconciliation.job_id)
            if active is not None and active.input_fingerprint == expected_input_fingerprint:
                return active
            active_id = active.id if active else None
            if previous_active_id is not None and active_id != previous_active_id:
                raise PositionReconciliationConcurrentUpdateError(
                    "Published reconciliation changed during processing"
                )
            if previous_active_id is None and active_id is not None:
                raise PositionReconciliationConcurrentUpdateError(
                    "A reconciliation was published during processing"
                )
            now = reconciliation.updated_at
            if active is not None:
                active.is_active = False
                active.superseded_at = now
                active.updated_at = now
            for assignment_id, assignment_row in tuple(self._assignments.items()):
                if assignment_row.job_id == reconciliation.job_id and assignment_row.is_active:
                    self._assignments[assignment_id] = replace(
                        assignment_row, is_active=False, superseded_at=now, updated_at=now
                    )
            reconciliation.status = ReconciliationStatus.COMPLETED
            reconciliation.is_active = True
            self._reconciliations[reconciliation.id] = reconciliation
            for assignment in assignments:
                self._assignments[assignment.id] = assignment
            return reconciliation

    def persist_revision_atomically(
        self,
        reconciliation: PositionReconciliation,
        assignments: Sequence[ProductPositionAssignment],
        previous_active_id: str | None,
    ) -> PositionReconciliation:
        return self.publish_completed_revision_atomically(
            reconciliation,
            assignments,
            previous_active_id,
            reconciliation.input_fingerprint,
        )

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
