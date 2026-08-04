"""Persistence port for local CSV import audits and row results."""

from __future__ import annotations

from typing import Protocol

from src.domain.local_csv_import.entities import LocalCsvImport


class LocalCsvImportRepository(Protocol):
    def get_by_id(self, import_id: str) -> LocalCsvImport | None: ...

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalCsvImport | None: ...

    def find_confirmed_secondary_keys(
        self, keys: set[tuple[str, str]]
    ) -> set[tuple[str, str]]: ...

    def save(self, record: LocalCsvImport) -> LocalCsvImport: ...
