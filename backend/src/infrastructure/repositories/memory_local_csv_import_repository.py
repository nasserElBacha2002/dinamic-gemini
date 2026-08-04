"""Process-local repository for local CSV imports."""

from __future__ import annotations

import threading

from src.domain.local_csv_import.entities import LocalCsvImport


class MemoryLocalCsvImportRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, LocalCsvImport] = {}
        self._lock = threading.Lock()

    def get_by_id(self, import_id: str) -> LocalCsvImport | None:
        return self._by_id.get((import_id or "").strip())

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalCsvImport | None:
        return next(
            (
                record
                for record in self._by_id.values()
                if record.inventory_id == inventory_id and record.export_id == export_id
            ),
            None,
        )

    def find_confirmed_secondary_keys(
        self, keys: set[tuple[str, str]]
    ) -> set[tuple[str, str]]:
        if not keys:
            return set()
        return {
            row.secondary_key
            for record in self._by_id.values()
            if record.status == "CONFIRMED"
            for row in record.rows
            if row.status == "IMPORTED" and row.secondary_key in keys
        }

    def save(self, record: LocalCsvImport) -> LocalCsvImport:
        with self._lock:
            by_export = self.get_by_export_id(
                inventory_id=record.inventory_id, export_id=record.export_id
            )
            if by_export is not None and by_export.id != record.id:
                raise ValueError("duplicate inventory_id + export_id")
            self._by_id[record.id] = record
        return record
