"""Port for preliminary detection reconciliation persistence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.preliminary_detection_reconciliations.entities import (
    PreliminaryDetectionReconciliation,
)


class ReconciliationUniqueViolationError(Exception):
    """Raised when INSERT hits UNIQUE(preliminary_detection_id, comparison_version, job_id)."""


class ReconciliationRowVersionConflictError(Exception):
    """Optimistic concurrency failure on update."""


class PreliminaryDetectionReconciliationRepository(Protocol):
    def get_by_id(self, reconciliation_id: str) -> PreliminaryDetectionReconciliation | None: ...

    def get_by_identity(
        self,
        *,
        preliminary_detection_id: str,
        comparison_version: str,
        job_id: str,
    ) -> PreliminaryDetectionReconciliation | None: ...

    def insert(
        self, row: PreliminaryDetectionReconciliation
    ) -> PreliminaryDetectionReconciliation: ...

    def update_if_version(
        self, row: PreliminaryDetectionReconciliation, *, expected_version: int
    ) -> PreliminaryDetectionReconciliation:
        """Update only if row_version matches; bump version. Raises conflict otherwise."""
        ...

    def list_by_aisle(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str | None = None,
        preliminary_detection_id: str | None = None,
        comparison_version: str | None = None,
        outcome: str | None = None,
        asset_id: str | None = None,
        client_file_id: str | None = None,
        parser_version: str | None = None,
        detector_version: str | None = None,
        comparable_only: bool | None = None,
        compared_after: datetime | None = None,
        compared_before: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Sequence[PreliminaryDetectionReconciliation]: ...

    def count_by_aisle(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str | None = None,
        preliminary_detection_id: str | None = None,
        comparison_version: str | None = None,
        outcome: str | None = None,
        asset_id: str | None = None,
        client_file_id: str | None = None,
        parser_version: str | None = None,
        detector_version: str | None = None,
        comparable_only: bool | None = None,
        compared_after: datetime | None = None,
        compared_before: datetime | None = None,
    ) -> int: ...

    def aggregate_metrics(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str | None = None,
        parser_version: str | None = None,
        detector_version: str | None = None,
    ) -> dict[str, int]: ...

    def claim_due(
        self,
        *,
        lease_token: str,
        lease_expires_at: datetime,
        now: datetime,
        limit: int = 50,
    ) -> Sequence[PreliminaryDetectionReconciliation]: ...

    def release_expired_leases(self, *, now: datetime) -> int: ...

    def list_by_preliminary_ids(
        self, preliminary_ids: Sequence[str]
    ) -> Sequence[PreliminaryDetectionReconciliation]: ...

    def delete_expired(self, *, now: datetime, limit: int = 500) -> int: ...
