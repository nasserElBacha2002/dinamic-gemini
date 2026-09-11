"""Persistence port for local CSV import audits and row results."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from src.application.ports.sql_cursor import SqlCursorLike
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    LocalCsvProductiveResult,
)


class LocalCsvProductiveApplier(Protocol):
    def __call__(
        self,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        *,
        cursor: SqlCursorLike | None = None,
    ) -> tuple[LocalCsvProductiveResult, ...]: ...


class LocalCsvImportRepository(Protocol):
    def get_by_id(self, import_id: str) -> LocalCsvImport | None: ...

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalCsvImport | None: ...

    def find_confirmed_secondary_keys(
        self,
        keys: set[tuple[str, str]],
        *,
        cursor: SqlCursorLike | None = None,
    ) -> set[tuple[str, str]]: ...

    def select_rows_to_import_on_cursor(
        self,
        cur: SqlCursorLike,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
    ) -> tuple[LocalCsvImport, tuple[LocalCsvImportRow, ...], bool]:
        """UPDLOCK import; return (record, rows_to_import, already_confirmed) without mutating."""
        ...

    def stage_or_get_existing(self, record: LocalCsvImport) -> LocalCsvImport:
        """Insert preview atomically; return existing on same export_id + content_hash."""
        ...

    def claim_import_for_materialization(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
        confirmed_by_user_id: str | None,
        apply_productive: LocalCsvProductiveApplier,
        clock_now: Callable[[], datetime],
        owner: str,
        lease_sec: int,
        cursor: SqlCursorLike | None = None,
    ) -> tuple[LocalCsvImport, bool]:
        """Atomically claim MATERIALIZING + apply productive staging when needed.

        Renamed semantics of the former ``confirm_import_atomically``: this does
        **not** mark CONFIRMED. Returns ``(record, already_confirmed)``.

        Raises ``LOCAL_CSV_MATERIALIZATION_IN_PROGRESS`` when another owner holds
        an active lease.
        """
        ...

    def confirm_import_atomically(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
        confirmed_by_user_id: str | None,
        apply_productive: LocalCsvProductiveApplier,
        clock_now: Callable[[], datetime],
        cursor: SqlCursorLike | None = None,
        owner: str | None = None,
        lease_sec: int = 120,
    ) -> tuple[LocalCsvImport, bool]:
        """Compatibility alias for ``claim_import_for_materialization``."""
        ...

    def finalize_import_confirmation_on_cursor(
        self,
        cur: SqlCursorLike,
        *,
        import_id: str,
        clock_now: Callable[[], datetime],
        confirmed_by_user_id: str | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
        require_inventory_writable_on_cursor: Callable[[SqlCursorLike, str], None]
        | None = None,
    ) -> LocalCsvImport:
        """Finalize to CONFIRMED on the caller's cursor (no nested transaction)."""
        ...

    def finalize_import_confirmation(
        self,
        *,
        import_id: str,
        clock_now: Callable[[], datetime],
        confirmed_by_user_id: str | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalCsvImport:
        """Own a transaction and call ``finalize_import_confirmation_on_cursor``."""
        ...

    def mark_materialization_failed(
        self,
        *,
        import_id: str,
        error_code: str,
        clock_now: Callable[[], datetime],
        requires_review: bool = False,
        next_retry_at: datetime | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalCsvImport:
        """Persist MATERIALIZATION_FAILED or REQUIRES_REVIEW with a stable error code."""
        ...

    def mark_materialization_failed_on_cursor(
        self,
        cur: SqlCursorLike,
        *,
        import_id: str,
        error_code: str,
        clock_now: Callable[[], datetime],
        requires_review: bool = False,
        next_retry_at: datetime | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalCsvImport:
        """Same as ``mark_materialization_failed`` on the caller's cursor."""
        ...

    def list_recovery_candidates(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> tuple[LocalCsvImport, ...]:
        """MATERIALIZING with expired lease or FAILED ready for retry."""
        ...

    def save(self, record: LocalCsvImport) -> LocalCsvImport: ...
