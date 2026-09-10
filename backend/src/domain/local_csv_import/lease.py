"""Lease claim helpers for import materialization (shared CSV/package rules)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.local_csv_import.entities import LocalCsvImport
from src.domain.local_csv_import.errors import (
    LOCAL_CSV_LEASE_LOST,
    LOCAL_CSV_MATERIALIZATION_IN_PROGRESS,
    LocalCsvImportError,
)
from src.domain.local_csv_import.statuses import (
    LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
    LOCAL_CSV_IMPORT_STATUS_PREVIEWED,
    LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW,
)


@dataclass(frozen=True)
class MaterializationLeaseClaim:
    owner: str
    lease_expires_at: datetime
    started_at: datetime
    last_attempt_at: datetime
    fencing_version: int
    attempts: int


def lease_is_active(record: LocalCsvImport, *, now: datetime) -> bool:
    expires = record.materialization_lease_expires_at
    if expires is None or not (record.materialization_owner or "").strip():
        return False
    return expires > now


def assert_owner_may_finalize(
    record: LocalCsvImport,
    *,
    owner: str | None,
    expected_fencing_version: int | None,
) -> None:
    if record.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
        return
    if owner is None:
        return
    current_owner = (record.materialization_owner or "").strip()
    if current_owner and current_owner != owner.strip():
        raise LocalCsvImportError(
            LOCAL_CSV_LEASE_LOST,
            "Materialization lease is held by another owner",
        )
    if (
        expected_fencing_version is not None
        and int(record.fencing_version) != int(expected_fencing_version)
    ):
        raise LocalCsvImportError(
            LOCAL_CSV_LEASE_LOST,
            "Materialization fencing version mismatch",
        )


def build_lease_claim(
    record: LocalCsvImport,
    *,
    now: datetime,
    owner: str,
    lease_sec: int,
) -> MaterializationLeaseClaim:
    owner_norm = (owner or "").strip()
    if not owner_norm:
        raise ValueError("materialization owner is required")
    if lease_sec < 5:
        raise ValueError("lease_sec must be >= 5")

    if record.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
        raise LocalCsvImportError(
            LOCAL_CSV_MATERIALIZATION_IN_PROGRESS,
            "Import is already confirmed",
        )
    if record.status == LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW:
        raise LocalCsvImportError(
            LOCAL_CSV_MATERIALIZATION_IN_PROGRESS,
            "Import requires review and cannot be claimed",
        )

    if record.status == LOCAL_CSV_IMPORT_STATUS_MATERIALIZING and lease_is_active(
        record, now=now
    ):
        # Active lease blocks all confirm re-entry (including same owner).
        # Long-running owners renew via an explicit renew_lease path, not Confirm.
        raise LocalCsvImportError(
            LOCAL_CSV_MATERIALIZATION_IN_PROGRESS,
            "Import materialization lease is active",
        )

    if record.status not in {
        LOCAL_CSV_IMPORT_STATUS_PREVIEWED,
        LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
        LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
    }:
        raise LocalCsvImportError(
            LOCAL_CSV_MATERIALIZATION_IN_PROGRESS,
            f"Import status {record.status!r} cannot be claimed",
        )

    takeover = record.status == LOCAL_CSV_IMPORT_STATUS_MATERIALIZING
    return MaterializationLeaseClaim(
        owner=owner_norm,
        lease_expires_at=now + timedelta(seconds=lease_sec),
        started_at=now if record.status == LOCAL_CSV_IMPORT_STATUS_PREVIEWED else (
            record.materialization_started_at or now
        ),
        last_attempt_at=now,
        fencing_version=int(record.fencing_version) + (1 if takeover else 0),
        attempts=int(record.materialization_attempts)
        + (0 if record.status == LOCAL_CSV_IMPORT_STATUS_PREVIEWED else 1),
    )
