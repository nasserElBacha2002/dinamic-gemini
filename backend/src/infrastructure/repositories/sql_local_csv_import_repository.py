"""SQL Server persistence for local CSV import audits and row results."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.database.sqlserver import SqlServerClient
from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow
from src.infrastructure.database.sql_transaction import sql_repository_cursor

_IMPORT_COLUMNS = (
    "id, export_id, schema_version, inventory_id, device_id, exported_at, status, "
    "content_hash, total_rows, valid_rows, rejected_rows, duplicate_rows, conflict_policy, "
    "confirmed_at, created_at, updated_at"
)
_ROW_COLUMNS = (
    "id, import_id, row_number, inventory_id, aisle_id, capture_session_id, capture_photo_id, "
    "client_file_id, capture_order, captured_at, position_code, internal_code, quantity, "
    "quantity_status, detection_status, source, requires_review, error_code, notes, status, "
    "validation_errors_json, validation_warnings_json"
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


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
        source=str(getattr(row, "source")),
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
    )


def _import_from_db(row: object, rows: tuple[LocalCsvImportRow, ...]) -> LocalCsvImport:
    return LocalCsvImport(
        id=str(getattr(row, "id")),
        export_id=str(getattr(row, "export_id")),
        schema_version=str(getattr(row, "schema_version")),
        inventory_id=str(getattr(row, "inventory_id")),
        device_id=str(getattr(row, "device_id")),
        exported_at=_utc(getattr(row, "exported_at")),
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
        created_at=_utc(getattr(row, "created_at")),
        updated_at=_utc(getattr(row, "updated_at")),
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
                found.update((str(row.capture_session_id), str(row.capture_photo_id)) for row in cur.fetchall())
        return found

    def save(self, record: LocalCsvImport) -> LocalCsvImport:
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
            record.updated_at,
            record.id,
        )
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                "UPDATE local_csv_imports SET export_id=?, schema_version=?, inventory_id=?, "
                "device_id=?, exported_at=?, status=?, content_hash=?, total_rows=?, valid_rows=?, "
                "rejected_rows=?, duplicate_rows=?, conflict_policy=?, confirmed_at=?, updated_at=? "
                "WHERE id=?",
                values,
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT INTO local_csv_imports "
                    "(id, export_id, schema_version, inventory_id, device_id, exported_at, status, "
                    "content_hash, total_rows, valid_rows, rejected_rows, duplicate_rows, "
                    "conflict_policy, confirmed_at, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (record.id, *values[:-2], record.created_at, record.updated_at),
                )
            cur.execute("DELETE FROM local_csv_import_rows WHERE import_id = ?", (record.id,))
            for row in record.rows:
                cur.execute(
                    "INSERT INTO local_csv_import_rows "
                    f"({_ROW_COLUMNS}) VALUES ({', '.join('?' for _ in range(22))})",
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
                        row.source,
                        row.requires_review,
                        row.error_code,
                        row.notes,
                        row.status,
                        json.dumps(row.validation_errors),
                        json.dumps(row.validation_warnings),
                    ),
                )
        return record
