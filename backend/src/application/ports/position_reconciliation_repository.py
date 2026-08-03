"""Persistence port for Phase 4 reconciliation revisions and assignments."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.domain.position_reconciliation.entities import (
    PositionReconciliation,
    ProductPositionAssignment,
)


class PositionReconciliationRepository(Protocol):
    def get_published_by_job(self, job_id: str) -> PositionReconciliation | None:
        """Return the active COMPLETED revision."""
        ...

    def get_last_attempt_by_job(self, job_id: str) -> PositionReconciliation | None:
        """Return the most recent attempt by creation time, regardless of status."""
        ...

    def get_active_by_job(self, job_id: str) -> PositionReconciliation | None:
        """Backward-compatible alias for get_published_by_job."""
        ...

    def get_by_id(self, reconciliation_id: str) -> PositionReconciliation | None: ...

    def mark_stale(self, job_id: str) -> PositionReconciliation | None: ...

    def begin_or_get_running(
        self, reconciliation: PositionReconciliation
    ) -> PositionReconciliation: ...

    def record_failed_attempt(
        self, attempt: PositionReconciliation
    ) -> PositionReconciliation:
        """Insert a non-active FAILED attempt without replacing the publication."""
        ...

    def publish_completed_revision_atomically(
        self,
        reconciliation: PositionReconciliation,
        assignments: Sequence[ProductPositionAssignment],
        previous_active_id: str | None,
        expected_input_fingerprint: str,
    ) -> PositionReconciliation: ...

    def persist_revision_atomically(
        self,
        reconciliation: PositionReconciliation,
        assignments: Sequence[ProductPositionAssignment],
        previous_active_id: str | None,
    ) -> PositionReconciliation: ...

    def list_active_assignments(self, job_id: str) -> Sequence[ProductPositionAssignment]: ...

    def list_result_assignment_history(
        self, job_id: str, result_id: str
    ) -> Sequence[ProductPositionAssignment]: ...

    def list_unassigned(self, job_id: str) -> Sequence[ProductPositionAssignment]: ...
