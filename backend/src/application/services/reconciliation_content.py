"""Canonical content compare for reconciliation idempotency (no blind overwrite)."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.preliminary_detection_reconciliations.entities import (
    PreliminaryDetectionReconciliation,
)


@dataclass(frozen=True)
class ReconciliationContent:
    preliminary_detection_id: str
    job_id: str
    comparison_version: str
    asset_id: str
    outcome: str
    not_comparable_reason: str | None
    local_status: str
    local_internal_code: str | None
    local_quantity: int | None
    remote_status: str | None
    remote_internal_code: str | None
    remote_quantity: int | None
    remote_result_id: str | None
    remote_result_fingerprint: str
    reconciliation_status: str


def content_from_row(row: PreliminaryDetectionReconciliation) -> ReconciliationContent:
    return ReconciliationContent(
        preliminary_detection_id=row.preliminary_detection_id,
        job_id=row.job_id,
        comparison_version=row.comparison_version,
        asset_id=row.asset_id,
        outcome=row.outcome,
        not_comparable_reason=row.not_comparable_reason,
        local_status=row.local_status,
        local_internal_code=row.local_internal_code,
        local_quantity=row.local_quantity,
        remote_status=row.remote_status,
        remote_internal_code=row.remote_internal_code,
        remote_quantity=row.remote_quantity,
        remote_result_id=row.remote_result_id,
        remote_result_fingerprint=row.remote_result_fingerprint or "PENDING",
        reconciliation_status=row.reconciliation_status,
    )


def same_terminal_content(a: ReconciliationContent, b: ReconciliationContent) -> bool:
    """Compare diagnostic payload (ignore lease/retry bookkeeping)."""
    return (
        a.preliminary_detection_id == b.preliminary_detection_id
        and a.job_id == b.job_id
        and a.comparison_version == b.comparison_version
        and a.asset_id == b.asset_id
        and a.outcome == b.outcome
        and a.not_comparable_reason == b.not_comparable_reason
        and a.local_status == b.local_status
        and a.local_internal_code == b.local_internal_code
        and a.local_quantity == b.local_quantity
        and a.remote_status == b.remote_status
        and a.remote_internal_code == b.remote_internal_code
        and a.remote_quantity == b.remote_quantity
        and a.remote_result_id == b.remote_result_id
        and a.remote_result_fingerprint == b.remote_result_fingerprint
    )


_TERMINAL = frozenset({"COMPLETED", "NOT_COMPARABLE", "FAILED_TERMINAL"})


def is_terminal_status(status: str) -> bool:
    return (status or "").upper() in _TERMINAL
