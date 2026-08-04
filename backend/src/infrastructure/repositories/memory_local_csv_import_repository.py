"""Process-local repository for local CSV imports."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    LocalCsvProductiveResult,
)
from src.domain.local_csv_import.errors import (
    LOCAL_CSV_EXPORT_CONFLICT,
    LOCAL_CSV_EXPORT_NOT_PREVIEWED,
    LOCAL_CSV_SECONDARY_CONFLICT,
    LocalCsvImportError,
)


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

    def stage_or_get_existing(self, record: LocalCsvImport) -> LocalCsvImport:
        with self._lock:
            existing = self.get_by_export_id(
                inventory_id=record.inventory_id, export_id=record.export_id
            )
            if existing is not None:
                if existing.content_hash != record.content_hash:
                    raise LocalCsvImportError(
                        LOCAL_CSV_EXPORT_CONFLICT,
                        "export_id already exists with different CSV content",
                    )
                return existing
            self._by_id[record.id] = record
            return record

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
        with self._lock:
            record = self.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
            if record is None:
                raise LocalCsvImportError(
                    LOCAL_CSV_EXPORT_NOT_PREVIEWED, "export_id has not been previewed"
                )
            if record.status == "CONFIRMED":
                return record, True

            eligible = {
                row.secondary_key for row in record.rows if row.status == "PREVIEW_VALID"
            }
            conflicts = self.find_confirmed_secondary_keys(eligible)
            if conflicts and conflict_policy == "REJECT":
                raise LocalCsvImportError(
                    LOCAL_CSV_SECONDARY_CONFLICT,
                    "One or more capture_session_id + capture_photo_id keys already exist",
                )

            to_import: list[LocalCsvImportRow] = []
            updated_rows: list[LocalCsvImportRow] = []
            for row in record.rows:
                if row.status != "PREVIEW_VALID":
                    updated_rows.append(row)
                    continue
                if row.secondary_key in conflicts:
                    updated_rows.append(replace(row, status="DUPLICATE"))
                    continue
                to_import.append(row)

            applied = apply_productive(record, tuple(to_import), confirmed_by_user_id)
            by_row_id = {r.import_row_id: r for r in applied}
            for row in to_import:
                result = by_row_id.get(row.id)
                updated_rows.append(
                    replace(
                        row,
                        status="IMPORTED",
                        productive_result_id=result.id if result else None,
                        requires_review=(
                            bool(result.requires_review) if result else row.requires_review
                        ),
                    )
                )

            # Preserve order by original row_number
            updated_rows.sort(key=lambda r: r.row_number)
            now = clock_now()
            confirmed = replace(
                record,
                status="CONFIRMED",
                valid_rows=sum(row.status == "IMPORTED" for row in updated_rows),
                duplicate_rows=sum(row.status == "DUPLICATE" for row in updated_rows),
                rejected_rows=sum(row.status == "REJECTED" for row in updated_rows),
                conflict_policy=conflict_policy,
                confirmed_at=now,
                confirmed_by_user_id=confirmed_by_user_id,
                updated_at=now,
                rows=tuple(updated_rows),
            )
            self._by_id[confirmed.id] = confirmed
            return confirmed, False

    def save(self, record: LocalCsvImport) -> LocalCsvImport:
        with self._lock:
            by_export = self.get_by_export_id(
                inventory_id=record.inventory_id, export_id=record.export_id
            )
            if by_export is not None and by_export.id != record.id:
                raise ValueError("duplicate inventory_id + export_id")
            self._by_id[record.id] = record
        return record
