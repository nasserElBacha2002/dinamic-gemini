"""SQL Server persistence for local CSV import audits and row results."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from src.database.sqlserver import SqlServerClient
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
from src.infrastructure.database.sql_transaction import sql_repository_cursor

_IMPORT_COLUMNS = (
    "id, export_id, schema_version, inventory_id, device_id, exported_at, status, "
    "content_hash, total_rows, valid_rows, rejected_rows, duplicate_rows, conflict_policy, "
    "confirmed_at, confirmed_by_user_id, created_at, updated_at"
)
_ROW_COLUMNS = (
    "id, import_id, row_number, inventory_id, aisle_id, capture_session_id, capture_photo_id, "
    "client_file_id, capture_order, captured_at, position_code, internal_code, quantity, "
    "quantity_status, detection_status, detection_source, ingestion_source, requires_review, "
    "error_code, notes, status, validation_errors_json, validation_warnings_json, "
    "productive_result_id"
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _utc_required(value: datetime | None, *, field: str) -> datetime:
    resolved = _utc(value)
    if resolved is None:
        raise ValueError(f"local_csv_imports.{field} is required")
    return resolved


def _json_tuple(value: object) -> tuple[str, ...]:
    if not value:
        return ()
    parsed = json.loads(str(value))
    return tuple(str(item) for item in parsed) if isinstance(parsed, list) else ()


def _row_from_db(row: object) -> LocalCsvImportRow:
    return LocalCsvImportRow(
        id=str(getattr(row, "id")),
        import_id=str(getattr(row, "import_id")),
        row_number=int(getattr(row, "row_number")),
        inventory_id=str(getattr(row, "inventory_id")),
        aisle_id=str(getattr(row, "aisle_id")),
        capture_session_id=str(getattr(row, "capture_session_id")),
        capture_photo_id=str(getattr(row, "capture_photo_id")),
        client_file_id=str(getattr(row, "client_file_id")),
        capture_order=(
            int(getattr(row, "capture_order"))
            if getattr(row, "capture_order", None) is not None
            else None
        ),
        captured_at=_utc(getattr(row, "captured_at", None)),
        position_code=str(getattr(row, "position_code")),
        internal_code=(
            str(getattr(row, "internal_code"))
            if getattr(row, "internal_code", None) is not None
            else None
        ),
        quantity=(
            int(getattr(row, "quantity")) if getattr(row, "quantity", None) is not None else None
        ),
        quantity_status=str(getattr(row, "quantity_status")),
        detection_status=str(getattr(row, "detection_status")),
        detection_source=str(getattr(row, "detection_source")),
        ingestion_source=str(getattr(row, "ingestion_source")),
        requires_review=bool(getattr(row, "requires_review")),
        error_code=(
            str(getattr(row, "error_code"))
            if getattr(row, "error_code", None) is not None
            else None
        ),
        notes=str(getattr(row, "notes")) if getattr(row, "notes", None) is not None else None,
        status=str(getattr(row, "status")),
        validation_errors=_json_tuple(getattr(row, "validation_errors_json", None)),
        validation_warnings=_json_tuple(getattr(row, "validation_warnings_json", None)),
        productive_result_id=(
            str(getattr(row, "productive_result_id"))
            if getattr(row, "productive_result_id", None) is not None
            else None
        ),
    )


def _import_from_db(row: object, rows: tuple[LocalCsvImportRow, ...]) -> LocalCsvImport:
    return LocalCsvImport(
        id=str(getattr(row, "id")),
        export_id=str(getattr(row, "export_id")),
        schema_version=str(getattr(row, "schema_version")),
        inventory_id=str(getattr(row, "inventory_id")),
        device_id=str(getattr(row, "device_id")),
        exported_at=_utc_required(getattr(row, "exported_at"), field="exported_at"),
        status=str(getattr(row, "status")),
        content_hash=str(getattr(row, "content_hash")),
        total_rows=int(getattr(row, "total_rows")),
        valid_rows=int(getattr(row, "valid_rows")),
        rejected_rows=int(getattr(row, "rejected_rows")),
        duplicate_rows=int(getattr(row, "duplicate_rows")),
        conflict_policy=(
            str(getattr(row, "conflict_policy"))
            if getattr(row, "conflict_policy", None) is not None
            else None
        ),
        confirmed_at=_utc(getattr(row, "confirmed_at", None)),
        confirmed_by_user_id=(
            str(getattr(row, "confirmed_by_user_id"))
            if getattr(row, "confirmed_by_user_id", None) is not None
            else None
        ),
        created_at=_utc_required(getattr(row, "created_at"), field="created_at"),
        updated_at=_utc_required(getattr(row, "updated_at"), field="updated_at"),
        rows=rows,
    )


class SqlLocalCsvImportRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_by_id(self, import_id: str) -> LocalCsvImport | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_IMPORT_COLUMNS} FROM local_csv_imports WHERE id = ?",
                ((import_id or "").strip(),),
            )
            record = cur.fetchone()
            if not record:
                return None
            cur.execute(
                f"SELECT {_ROW_COLUMNS} FROM local_csv_import_rows "
                "WHERE import_id = ? ORDER BY row_number",
                ((import_id or "").strip(),),
            )
            rows = tuple(_row_from_db(row) for row in cur.fetchall())
        return _import_from_db(record, rows)

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalCsvImport | None:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT id FROM local_csv_imports WHERE inventory_id = ? AND export_id = ?",
                (inventory_id, export_id),
            )
            row = cur.fetchone()
        return self.get_by_id(str(row.id)) if row else None

    def find_confirmed_secondary_keys(
        self, keys: set[tuple[str, str]]
    ) -> set[tuple[str, str]]:
        found: set[tuple[str, str]] = set()
        ordered = list(keys)
        for offset in range(0, len(ordered), 500):
            batch = ordered[offset : offset + 500]
            predicates = " OR ".join(
                "(r.capture_session_id = ? AND r.capture_photo_id = ?)" for _ in batch
            )
            params = tuple(item for key in batch for item in key)
            with self._client.cursor() as cur:
                cur.execute(
                    "SELECT r.capture_session_id, r.capture_photo_id "
                    "FROM local_csv_import_rows r "
                    "JOIN local_csv_imports i ON i.id = r.import_id "
                    "WHERE i.status = 'CONFIRMED' AND r.status = 'IMPORTED' "
                    f"AND ({predicates})",
                    params,
                )
                found.update(
                    (str(row.capture_session_id), str(row.capture_photo_id))
                    for row in cur.fetchall()
                )
        return found

    def stage_or_get_existing(self, record: LocalCsvImport) -> LocalCsvImport:
        try:
            return self.save(record)
        except Exception as exc:
            # Narrow: only IntegrityError / SQL unique (2627/2601) become idempotent replay.
            if not _is_unique_violation(exc):
                raise
            existing = self.get_by_export_id(
                inventory_id=record.inventory_id, export_id=record.export_id
            )
            if existing is None:
                raise
            if existing.content_hash != record.content_hash:
                raise LocalCsvImportError(
                    LOCAL_CSV_EXPORT_CONFLICT,
                    "export_id already exists with different CSV content",
                ) from exc
            return existing

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
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                f"SELECT {_IMPORT_COLUMNS} FROM local_csv_imports WITH (UPDLOCK, ROWLOCK) "
                "WHERE inventory_id = ? AND export_id = ?",
                (inventory_id, export_id),
            )
            header = cur.fetchone()
            if not header:
                raise LocalCsvImportError(
                    LOCAL_CSV_EXPORT_NOT_PREVIEWED, "export_id has not been previewed"
                )
            cur.execute(
                f"SELECT {_ROW_COLUMNS} FROM local_csv_import_rows "
                "WHERE import_id = ? ORDER BY row_number",
                (str(header.id),),
            )
            rows = tuple(_row_from_db(row) for row in cur.fetchall())
            record = _import_from_db(header, rows)
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

            # Must use the caller-provided callback (CSV writer or package
            # materializer+writer). Do not bypass it with self._writer — package
            # confirm injects source-asset materialization here.
            applied = apply_productive(
                record, tuple(to_import), confirmed_by_user_id
            )
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
            self._persist(cur, confirmed)
            return confirmed, False

    def save(self, record: LocalCsvImport) -> LocalCsvImport:
        with sql_repository_cursor(self._client) as cur:
            self._persist(cur, record)
        return record

    def _persist(self, cur: object, record: LocalCsvImport) -> None:
        values = (
            record.export_id,
            record.schema_version,
            record.inventory_id,
            record.device_id,
            record.exported_at,
            record.status,
            record.content_hash,
            record.total_rows,
            record.valid_rows,
            record.rejected_rows,
            record.duplicate_rows,
            record.conflict_policy,
            record.confirmed_at,
            record.confirmed_by_user_id,
            record.updated_at,
            record.id,
        )
        cur.execute(  # type: ignore[attr-defined]
            "UPDATE local_csv_imports SET export_id=?, schema_version=?, inventory_id=?, "
            "device_id=?, exported_at=?, status=?, content_hash=?, total_rows=?, valid_rows=?, "
            "rejected_rows=?, duplicate_rows=?, conflict_policy=?, confirmed_at=?, "
            "confirmed_by_user_id=?, updated_at=? WHERE id=?",
            values,
        )
        if cur.rowcount == 0:  # type: ignore[attr-defined]
            cur.execute(  # type: ignore[attr-defined]
                "INSERT INTO local_csv_imports "
                "(id, export_id, schema_version, inventory_id, device_id, exported_at, status, "
                "content_hash, total_rows, valid_rows, rejected_rows, duplicate_rows, "
                "conflict_policy, confirmed_at, confirmed_by_user_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record.id, *values[:-2], record.created_at, record.updated_at),
            )
        # Upsert rows in place. Never DELETE+re-INSERT after productive results exist:
        # FK_local_csv_productive_row references import_row_id.
        keep_ids = {row.id for row in record.rows}
        for row in record.rows:
            row_values = (
                row.import_id,
                row.row_number,
                row.inventory_id,
                row.aisle_id,
                row.capture_session_id,
                row.capture_photo_id,
                row.client_file_id,
                row.capture_order,
                row.captured_at,
                row.position_code,
                row.internal_code,
                row.quantity,
                row.quantity_status,
                row.detection_status,
                row.detection_source,
                row.ingestion_source,
                row.requires_review,
                row.error_code,
                row.notes,
                row.status,
                json.dumps(row.validation_errors),
                json.dumps(row.validation_warnings),
                row.productive_result_id,
                row.id,
            )
            cur.execute(  # type: ignore[attr-defined]
                "UPDATE local_csv_import_rows SET import_id=?, row_number=?, inventory_id=?, "
                "aisle_id=?, capture_session_id=?, capture_photo_id=?, client_file_id=?, "
                "capture_order=?, captured_at=?, position_code=?, internal_code=?, quantity=?, "
                "quantity_status=?, detection_status=?, detection_source=?, ingestion_source=?, "
                "requires_review=?, error_code=?, notes=?, status=?, validation_errors_json=?, "
                "validation_warnings_json=?, productive_result_id=? WHERE id=?",
                row_values,
            )
            if cur.rowcount == 0:  # type: ignore[attr-defined]
                cur.execute(  # type: ignore[attr-defined]
                    "INSERT INTO local_csv_import_rows "
                    f"({_ROW_COLUMNS}) VALUES ({', '.join('?' for _ in range(24))})",
                    (
                        row.id,
                        row.import_id,
                        row.row_number,
                        row.inventory_id,
                        row.aisle_id,
                        row.capture_session_id,
                        row.capture_photo_id,
                        row.client_file_id,
                        row.capture_order,
                        row.captured_at,
                        row.position_code,
                        row.internal_code,
                        row.quantity,
                        row.quantity_status,
                        row.detection_status,
                        row.detection_source,
                        row.ingestion_source,
                        row.requires_review,
                        row.error_code,
                        row.notes,
                        row.status,
                        json.dumps(row.validation_errors),
                        json.dumps(row.validation_warnings),
                        row.productive_result_id,
                    ),
                )
        if keep_ids:
            placeholders = ", ".join("?" for _ in keep_ids)
            cur.execute(  # type: ignore[attr-defined]
                "DELETE FROM local_csv_import_rows WHERE import_id = ? AND id NOT IN "
                f"({placeholders}) AND NOT EXISTS ("
                "SELECT 1 FROM local_csv_productive_results p "
                "WHERE p.import_row_id = local_csv_import_rows.id)",
                (record.id, *keep_ids),
            )
        else:
            cur.execute(  # type: ignore[attr-defined]
                "DELETE FROM local_csv_import_rows WHERE import_id = ? AND NOT EXISTS ("
                "SELECT 1 FROM local_csv_productive_results p "
                "WHERE p.import_row_id = local_csv_import_rows.id)",
                (record.id,),
            )


def _is_unique_violation(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {"IntegrityError", "UniqueViolation", "UniqueConstraintError"}:
        return True
    args = getattr(exc, "args", ())
    for arg in args:
        text = str(arg)
        if "2627" in text or "2601" in text or "UX_local_csv_imports_inventory_export" in text:
            return True
    return False
