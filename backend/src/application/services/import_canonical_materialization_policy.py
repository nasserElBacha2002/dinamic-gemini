"""Raise hard domain errors from canonical import materialization outcomes."""

from __future__ import annotations

from src.application.services.import_canonical_position_materializer import (
    ImportCanonicalMaterializationSummary,
)
from src.domain.inventory.write_policy import InventoryWriteDenialCode
from src.domain.local_csv_import.error_codes import (
    LOCAL_CSV_CANONICAL_MATERIALIZATION_REJECTED,
    LOCAL_CSV_MATERIALIZATION_FAILED,
)
from src.domain.local_csv_import.errors import (
    INVENTORY_CLOSED,
    INVENTORY_NOT_WRITABLE,
    LocalCsvImportError,
)
from src.domain.position_materialization.entities import PositionMaterializationStatus

_PERMANENT_STATUSES = frozenset(
    {
        PositionMaterializationStatus.REJECTED_VALIDATION,
        PositionMaterializationStatus.REJECTED_SCOPE,
        PositionMaterializationStatus.REJECTED_IDEMPOTENCY_CONFLICT,
        PositionMaterializationStatus.REJECTED_IDENTITY_CONFLICT,
        PositionMaterializationStatus.REJECTED_CONFLICT,
    }
)

_RETRYABLE_STATUSES = frozenset(
    {
        PositionMaterializationStatus.RETRYABLE_FAILURE,
        PositionMaterializationStatus.INVARIANT_VIOLATION,
    }
)


class CanonicalImportMaterializationOutcome(Exception):
    """Carries the last materialization status for caller classification."""

    def __init__(
        self,
        *,
        status: PositionMaterializationStatus,
        error_code: str | None,
        detail: str,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.error_code = error_code
        self.detail = detail


def raise_for_canonical_failures(
    summary: ImportCanonicalMaterializationSummary,
) -> None:
    """Fail closed when enabled materialization did not fully succeed."""
    if summary.failed <= 0:
        return
    status = None
    if summary.last_status:
        try:
            status = PositionMaterializationStatus(summary.last_status)
        except ValueError:
            status = None
    if status is PositionMaterializationStatus.REJECTED_INVENTORY_STATE:
        code = (summary.last_error_code or "").strip() or INVENTORY_NOT_WRITABLE
        if code == InventoryWriteDenialCode.INVENTORY_CLOSED.value or code == INVENTORY_CLOSED:
            raise LocalCsvImportError(
                INVENTORY_CLOSED, summary.last_detail or "Inventory closed"
            )
        raise LocalCsvImportError(
            INVENTORY_NOT_WRITABLE, summary.last_detail or "Inventory is not writable"
        )
    if status in _PERMANENT_STATUSES:
        raise LocalCsvImportError(
            LOCAL_CSV_CANONICAL_MATERIALIZATION_REJECTED,
            summary.last_detail
            or "Canonical position materialization rejected; import requires review",
        )
    if status in _RETRYABLE_STATUSES or status is None:
        raise LocalCsvImportError(
            LOCAL_CSV_MATERIALIZATION_FAILED,
            summary.last_detail or "Canonical position materialization failed",
        )
    raise LocalCsvImportError(
        LOCAL_CSV_CANONICAL_MATERIALIZATION_REJECTED,
        summary.last_detail or f"Canonical materialization ended with {status}",
    )
