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
    ) -> tuple[LocalCsvImport, bool]:
        """Lock inventory+export, apply productive rows, mark CONFIRMED in one transaction.

        When ``cursor`` is provided, the caller owns the surrounding transaction
        (no nested commit). ``apply_productive`` receives ``cursor=`` for shared TX writes.
        """
        ...

    def save(self, record: LocalCsvImport) -> LocalCsvImport: ...
