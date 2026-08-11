"""Process-local repository for local CSV imports."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from src.application.ports.local_csv_import_repository import LocalCsvProductiveApplier
from src.application.ports.sql_cursor import SqlCursorLike
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
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
        self,
        keys: set[tuple[str, str]],
        *,
        cursor: SqlCursorLike | None = None,
    ) -> set[tuple[str, str]]:
        _ = cursor
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

    def select_rows_to_import_on_cursor(
        self,
        cur: SqlCursorLike,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
    ) -> tuple[LocalCsvImport, tuple[LocalCsvImportRow, ...], bool]:
        _ = cur
        record = self.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
        if record is None:
            raise LocalCsvImportError(
                LOCAL_CSV_EXPORT_NOT_PREVIEWED, "export_id has not been previewed"
            )
        if record.status == "CONFIRMED":
            return record, (), True

        eligible = {
            row.secondary_key for row in record.rows if row.status == "PREVIEW_VALID"
        }
        conflict_keys = self.find_confirmed_secondary_keys(eligible)
        if conflict_keys and conflict_policy == "REJECT":
            raise LocalCsvImportError(
                LOCAL_CSV_SECONDARY_CONFLICT,
                "One or more capture_session_id + capture_photo_id keys already exist",
            )

        to_import = tuple(
            row
            for row in record.rows
            if row.status == "PREVIEW_VALID" and row.secondary_key not in conflict_keys
        )
        return record, to_import, False

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
        with self._lock:
            record, to_import, already_confirmed = self.select_rows_to_import_on_cursor(
                cursor,  # type: ignore[arg-type]
                inventory_id=inventory_id,
                export_id=export_id,
                conflict_policy=conflict_policy,
            )
            if already_confirmed:
                return record, True

            conflict_keys = self.find_confirmed_secondary_keys(
                {row.secondary_key for row in record.rows if row.status == "PREVIEW_VALID"}
            )

            applied = apply_productive(
                record, to_import, confirmed_by_user_id, cursor=cursor
            )
            by_row_id = {r.import_row_id: r for r in applied}
            updated_rows: list[LocalCsvImportRow] = []
            for row in record.rows:
                if row.status != "PREVIEW_VALID":
                    updated_rows.append(row)
                    continue
                if row.secondary_key in conflict_keys:
                    updated_rows.append(replace(row, status="DUPLICATE"))
                    continue
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
