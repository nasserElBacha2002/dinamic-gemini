"""Persistence port for local CSV import audits and row results."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow, LocalCsvProductiveResult


class LocalCsvImportRepository(Protocol):
    def get_by_id(self, import_id: str) -> LocalCsvImport | None: ...

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalCsvImport | None: ...

    def find_confirmed_secondary_keys(
        self, keys: set[tuple[str, str]]
    ) -> set[tuple[str, str]]: ...

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
        apply_productive: Callable[
            [LocalCsvImport, tuple[LocalCsvImportRow, ...], str | None],
            tuple[LocalCsvProductiveResult, ...],
        ],
        clock_now: Callable[[], datetime],
    ) -> tuple[LocalCsvImport, bool]:
        """Lock inventory+export, apply productive rows, mark CONFIRMED in one transaction."""
        ...

    def save(self, record: LocalCsvImport) -> LocalCsvImport: ...
