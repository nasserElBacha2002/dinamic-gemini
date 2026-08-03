"""Persistence port for Phase 4 reconciliation revisions and assignments."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.domain.position_reconciliation.entities import (
    PositionReconciliation,
    ProductPositionAssignment,
)


class PositionReconciliationRepository(Protocol):
    def get_active_by_job(self, job_id: str) -> PositionReconciliation | None: ...

    def get_by_id(self, reconciliation_id: str) -> PositionReconciliation | None: ...

    def mark_stale(self, job_id: str) -> PositionReconciliation | None: ...

    def begin_or_get_running(
        self, reconciliation: PositionReconciliation
    ) -> PositionReconciliation: ...

    def persist_revision_atomically(
        self,
        reconciliation: PositionReconciliation,
        assignments: Sequence[ProductPositionAssignment],
        previous_active_id: str | None,
    ) -> PositionReconciliation: ...

    def list_active_assignments(self, job_id: str) -> Sequence[ProductPositionAssignment]: ...

    def list_unassigned(self, job_id: str) -> Sequence[ProductPositionAssignment]: ...
