"""Job-scoped delete/count for transactional result replacement (Phase 2 Part 2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class JobScopeRowCounts:
    positions: int
    products: int
    evidence: int
    raw_labels: int
    normalized_labels: int
    final_counts: int


@runtime_checkable
class JobResultScopeStore(Protocol):
    """Delete or count rows for one ``(inventory_id, aisle_id, job_id)`` snapshot."""

    def count_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobScopeRowCounts: ...

    def delete_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobScopeRowCounts:
        """Remove prior snapshot for ``job_id`` only. Returns pre-delete counts."""
        ...
