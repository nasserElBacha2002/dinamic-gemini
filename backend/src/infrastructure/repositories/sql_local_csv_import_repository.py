"""SQL Server persistence for local CSV import audits and row results."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from src.application.ports.local_csv_import_repository import LocalCsvProductiveApplier
from src.application.ports.sql_cursor import SqlCursorLike
from src.database.sqlserver import SqlServerClient
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
)
from src.domain.local_csv_import.error_codes import normalize_stable_error_code
from src.domain.local_csv_import.errors import (
    LOCAL_CSV_EXPORT_CONFLICT,
    LOCAL_CSV_EXPORT_NOT_PREVIEWED,
    LOCAL_CSV_IMPORT_INVALID_STATUS,
    LOCAL_CSV_MATERIALIZATION_FAILED,
    LOCAL_CSV_SECONDARY_CONFLICT,
    LocalCsvImportError,
)
from src.domain.local_csv_import.lease import (
    assert_owner_may_finalize,
    build_lease_claim,
)
from src.domain.local_csv_import.statuses import (
    LOCAL_CSV_IMPORT_RESUMABLE_STATUSES,
    LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
    LOCAL_CSV_IMPORT_STATUS_PREVIEWED,
    LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW,
)
from src.infrastructure.database.sql_batch import (
    EXECUTEMANY_IMPORT_ROW_PARAM_SET_CHUNK,
    SQL_VALUES_PAIR_CHUNK_SIZE,
    chunked,
    cursor_executemany,
)
from src.infrastructure.database.sql_inventory_write_policy import (
    default_require_inventory_writable_on_cursor,
)
from src.infrastructure.database.sql_transaction import sql_repository_cursor

# Must stay aligned with ``local_csv_row_secondary_key`` prefixes.
_SECONDARY_KEY_PREFIXES = ("label:", "pos:", "photo:")


def partition_secondary_key_candidates(
    keys: set[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Split secondary keys into (label pairs, photo/pos pairs).

    Raises ``ValueError`` for unknown suffixes so new key shapes fail loudly until
    the candidate-scoped SQL is updated.
    """
    label_pairs: list[tuple[str, str]] = []
    photo_pairs: list[tuple[str, str]] = []
    for session, suffix in keys:
        if suffix.startswith("label:"):
            label_pairs.append((session, suffix[len("label:") :]))
        elif suffix.startswith("pos:"):
            photo_pairs.append((session, suffix[len("pos:") :]))
        elif suffix.startswith("photo:"):
            photo_pairs.append((session, suffix[len("photo:") :]))
        else:
            raise ValueError(
                "unsupported local_csv secondary_key suffix "
                f"{suffix!r}; expected one of {_SECONDARY_KEY_PREFIXES}"
            )
    return label_pairs, photo_pairs


_IMPORT_COLUMNS = (
    "id, export_id, schema_version, inventory_id, device_id, exported_at, status, "
    "content_hash, total_rows, valid_rows, rejected_rows, duplicate_rows, conflict_policy, "
    "confirmed_at, confirmed_by_user_id, source_metadata_json, last_error_code, "
    "materialization_attempts, materialization_owner, materialization_lease_expires_at, "
    "materialization_started_at, materialization_last_attempt_at, materialization_next_retry_at, "
    "fencing_version, created_at, updated_at"
)
_CLAIMED_STATUS_SQL = (
    "('CONFIRMED', 'MATERIALIZING', 'MATERIALIZATION_FAILED')"
)
_ROW_COLUMNS = (
    "id, import_id, row_number, inventory_id, aisle_id, capture_session_id, capture_photo_id, "
    "client_file_id, capture_order, captured_at, position_code, internal_code, quantity, "
    "quantity_status, detection_status, detection_source, ingestion_source, requires_review, "
    "error_code, notes, status, validation_errors_json, validation_warnings_json, "
    "productive_result_id, label_id, position_label_id, position_payload_raw"
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
        label_id=(
            str(getattr(row, "label_id")).strip().upper() or None
            if getattr(row, "label_id", None) is not None
            else None
        ),
        position_label_id=(
            str(getattr(row, "position_label_id")).strip() or None
            if getattr(row, "position_label_id", None) is not None
            else None
        ),
        position_payload_raw=(
            str(getattr(row, "position_payload_raw")).strip() or None
            if getattr(row, "position_payload_raw", None) is not None
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
        source_metadata_json=(
            str(getattr(row, "source_metadata_json"))
            if getattr(row, "source_metadata_json", None) is not None
            else None
        ),
        last_error_code=(
            str(getattr(row, "last_error_code")).strip() or None
            if getattr(row, "last_error_code", None) is not None
            else None
        ),
        materialization_attempts=int(getattr(row, "materialization_attempts", 0) or 0),
        materialization_owner=(
            str(getattr(row, "materialization_owner")).strip() or None
            if getattr(row, "materialization_owner", None) is not None
            else None
        ),
        materialization_lease_expires_at=_utc(
            getattr(row, "materialization_lease_expires_at", None)
        ),
        materialization_started_at=_utc(getattr(row, "materialization_started_at", None)),
        materialization_last_attempt_at=_utc(
            getattr(row, "materialization_last_attempt_at", None)
        ),
        materialization_next_retry_at=_utc(
            getattr(row, "materialization_next_retry_at", None)
        ),
        fencing_version=int(getattr(row, "fencing_version", 0) or 0),
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
        self,
        keys: set[tuple[str, str]],
        *,
        cursor: SqlCursorLike | None = None,
    ) -> set[tuple[str, str]]:
        """Return intersection of ``keys`` with already-IMPORTED confirmed secondary keys.

        Candidate-scoped: join VALUES of requested (session, label|photo) pairs instead of
        scanning all historical CONFIRMED/IMPORTED rows into Python.
        """
        from src.domain.local_csv_import.entities import local_csv_row_secondary_key

        if not keys:
            return set()

        label_pairs, photo_pairs = partition_secondary_key_candidates(keys)
        found: set[tuple[str, str]] = set()

        def _consume_rows(rows: Sequence[Any]) -> None:
            for row in rows:
                key = local_csv_row_secondary_key(
                    capture_session_id=str(row.capture_session_id),
                    capture_photo_id=str(row.capture_photo_id),
                    label_id=(str(row.label_id).strip() if row.label_id else None),
                    detection_source=(
                        str(row.detection_source).strip() if row.detection_source else None
                    ),
                )
                if key in keys:
                    found.add(key)

        def _scan(cur: SqlCursorLike) -> None:
            for chunk in chunked(label_pairs, SQL_VALUES_PAIR_CHUNK_SIZE):
                values_sql = ", ".join("(?, ?)" for _ in chunk)
                flat: list[str] = [v for pair in chunk for v in pair]
                cur.execute(
                    "SELECT r.capture_session_id, r.capture_photo_id, r.label_id, r.detection_source "
                    "FROM local_csv_import_rows r "
                    "JOIN local_csv_imports i ON i.id = r.import_id "
                    f"INNER JOIN (VALUES {values_sql}) AS c(session_id, label_id) "
                    "ON c.session_id = r.capture_session_id AND c.label_id = r.label_id "
                    "WHERE i.status IN "
                    f"{_CLAIMED_STATUS_SQL} AND r.status = 'IMPORTED' "
                    "AND r.label_id IS NOT NULL",
                    tuple(flat),
                )
                _consume_rows(cur.fetchall())

            for chunk in chunked(photo_pairs, SQL_VALUES_PAIR_CHUNK_SIZE):
                values_sql = ", ".join("(?, ?)" for _ in chunk)
                flat = [v for pair in chunk for v in pair]
                cur.execute(
                    "SELECT r.capture_session_id, r.capture_photo_id, r.label_id, r.detection_source "
                    "FROM local_csv_import_rows r "
                    "JOIN local_csv_imports i ON i.id = r.import_id "
                    f"INNER JOIN (VALUES {values_sql}) AS c(session_id, photo_id) "
                    "ON c.session_id = r.capture_session_id "
                    "AND c.photo_id = r.capture_photo_id "
                    "WHERE i.status IN "
                    f"{_CLAIMED_STATUS_SQL} AND r.status = 'IMPORTED' "
                    "AND r.label_id IS NULL",
                    tuple(flat),
                )
                _consume_rows(cur.fetchall())

        if cursor is not None:
            _scan(cursor)
        else:
            with self._client.cursor() as cur:
                _scan(cur)
        return found

    def find_confirmed_secondary_keys_full_scan(
        self,
        keys: set[tuple[str, str]],
        *,
        cursor: SqlCursorLike | None = None,
    ) -> set[tuple[str, str]]:
        """Legacy full-scan semantics — used for parity tests only (not hot path)."""
        from src.domain.local_csv_import.entities import local_csv_row_secondary_key

        if not keys:
            return set()
        # Validate prefixes even on the legacy path so unknown key shapes fail loudly.
        partition_secondary_key_candidates(keys)
        found: set[tuple[str, str]] = set()

        def _scan(cur: SqlCursorLike) -> None:
            cur.execute(
                "SELECT r.capture_session_id, r.capture_photo_id, r.label_id, r.detection_source "
                "FROM local_csv_import_rows r "
                "JOIN local_csv_imports i ON i.id = r.import_id "
                "WHERE i.status IN "
                f"{_CLAIMED_STATUS_SQL} AND r.status = 'IMPORTED'"
            )
            for row in cur.fetchall():
                key = local_csv_row_secondary_key(
                    capture_session_id=str(row.capture_session_id),
                    capture_photo_id=str(row.capture_photo_id),
                    label_id=(str(row.label_id).strip() if row.label_id else None),
                    detection_source=(
                        str(row.detection_source).strip() if row.detection_source else None
                    ),
                )
                if key in keys:
                    found.add(key)

        if cursor is not None:
            _scan(cursor)
        else:
            with self._client.cursor() as cur:
                _scan(cur)
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

    def select_rows_to_import_on_cursor(
        self,
        cur: SqlCursorLike,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
    ) -> tuple[LocalCsvImport, tuple[LocalCsvImportRow, ...], bool]:
        """UPDLOCK import, resolve conflicts, return rows to import without mutating."""
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
        if record.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
            return record, (), True
        if record.status in LOCAL_CSV_IMPORT_RESUMABLE_STATUSES:
            # Productive rows already claimed; resume materialization only.
            return record, (), False
        if record.status != LOCAL_CSV_IMPORT_STATUS_PREVIEWED:
            raise LocalCsvImportError(
                LOCAL_CSV_IMPORT_INVALID_STATUS,
                f"Import status {record.status!r} cannot be confirmed",
            )

        eligible = {
            row.secondary_key for row in record.rows if row.status == "PREVIEW_VALID"
        }
        conflict_keys = self.find_confirmed_secondary_keys(eligible, cursor=cur)
        if conflict_keys and conflict_policy == "REJECT":
            raise LocalCsvImportError(
                LOCAL_CSV_SECONDARY_CONFLICT,
                "One or more capture_session_id + capture_photo_id keys already exist",
            )

        to_import: list[LocalCsvImportRow] = []
        for row in record.rows:
            if row.status != "PREVIEW_VALID":
                continue
            if row.secondary_key in conflict_keys:
                continue
            to_import.append(row)
        return record, tuple(to_import), False

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
        if cursor is not None:
            return self._claim_import_on_cursor(
                cursor,
                inventory_id=inventory_id,
                export_id=export_id,
                conflict_policy=conflict_policy,
                confirmed_by_user_id=confirmed_by_user_id,
                apply_productive=apply_productive,
                clock_now=clock_now,
                owner=owner,
                lease_sec=lease_sec,
            )
        with self._client.begin_transaction() as txn:
            with sql_repository_cursor(self._client, connection=txn.connection) as cur:
                result = self._claim_import_on_cursor(
                    cur,
                    inventory_id=inventory_id,
                    export_id=export_id,
                    conflict_policy=conflict_policy,
                    confirmed_by_user_id=confirmed_by_user_id,
                    apply_productive=apply_productive,
                    clock_now=clock_now,
                    owner=owner,
                    lease_sec=lease_sec,
                )
            txn.commit()
            return result

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
        resolved_owner = (owner or confirmed_by_user_id or "system-import").strip()
        return self.claim_import_for_materialization(
            inventory_id=inventory_id,
            export_id=export_id,
            conflict_policy=conflict_policy,
            confirmed_by_user_id=confirmed_by_user_id,
            apply_productive=apply_productive,
            clock_now=clock_now,
            owner=resolved_owner,
            lease_sec=lease_sec,
            cursor=cursor,
        )

    def _claim_import_on_cursor(
        self,
        cur: SqlCursorLike,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
        confirmed_by_user_id: str | None,
        apply_productive: LocalCsvProductiveApplier,
        clock_now: Callable[[], datetime],
        owner: str,
        lease_sec: int,
    ) -> tuple[LocalCsvImport, bool]:
        record, to_import, already_confirmed = self.select_rows_to_import_on_cursor(
            cur,
            inventory_id=inventory_id,
            export_id=export_id,
            conflict_policy=conflict_policy,
        )
        if already_confirmed:
            return record, True

        now = clock_now()
        claim = build_lease_claim(
            record, now=now, owner=owner, lease_sec=lease_sec
        )

        if record.status in LOCAL_CSV_IMPORT_RESUMABLE_STATUSES:
            resumed = replace(
                record,
                status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
                conflict_policy=conflict_policy or record.conflict_policy,
                confirmed_by_user_id=confirmed_by_user_id or record.confirmed_by_user_id,
                last_error_code=None,
                materialization_attempts=claim.attempts,
                materialization_owner=claim.owner,
                materialization_lease_expires_at=claim.lease_expires_at,
                materialization_started_at=claim.started_at,
                materialization_last_attempt_at=claim.last_attempt_at,
                materialization_next_retry_at=None,
                fencing_version=claim.fencing_version,
                updated_at=now,
            )
            self._persist(cur, resumed)
            return resumed, False

        conflict_keys = self.find_confirmed_secondary_keys(
            {row.secondary_key for row in record.rows if row.status == "PREVIEW_VALID"},
            cursor=cur,
        )

        applied = apply_productive(
            record, to_import, confirmed_by_user_id, cursor=cur
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
        materializing = replace(
            record,
            status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
            valid_rows=sum(row.status == "IMPORTED" for row in updated_rows),
            duplicate_rows=sum(row.status == "DUPLICATE" for row in updated_rows),
            rejected_rows=sum(row.status == "REJECTED" for row in updated_rows),
            conflict_policy=conflict_policy,
            confirmed_at=None,
            confirmed_by_user_id=confirmed_by_user_id,
            last_error_code=None,
            materialization_attempts=claim.attempts,
            materialization_owner=claim.owner,
            materialization_lease_expires_at=claim.lease_expires_at,
            materialization_started_at=claim.started_at,
            materialization_last_attempt_at=claim.last_attempt_at,
            materialization_next_retry_at=None,
            fencing_version=claim.fencing_version,
            updated_at=now,
            rows=tuple(updated_rows),
        )
        self._persist(cur, materializing)
        return materializing, False

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
        cur.execute(
            f"SELECT {_IMPORT_COLUMNS} FROM local_csv_imports "
            "WITH (UPDLOCK, ROWLOCK) WHERE id = ?",
            ((import_id or "").strip(),),
        )
        header = cur.fetchone()
        if header is None:
            raise LocalCsvImportError(
                LOCAL_CSV_EXPORT_NOT_PREVIEWED, "import not found"
            )
        cur.execute(
            f"SELECT {_ROW_COLUMNS} FROM local_csv_import_rows "
            "WHERE import_id = ? ORDER BY row_number",
            (str(header.id),),
        )
        rows = tuple(_row_from_db(row) for row in cur.fetchall())
        record = _import_from_db(header, rows)
        if record.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
            return record
        assert_owner_may_finalize(
            record,
            owner=owner,
            expected_fencing_version=expected_fencing_version,
        )
        if record.status not in LOCAL_CSV_IMPORT_RESUMABLE_STATUSES:
            raise LocalCsvImportError(
                LOCAL_CSV_IMPORT_INVALID_STATUS,
                f"Import status {record.status!r} cannot be finalized",
            )
        checker = (
            require_inventory_writable_on_cursor
            or default_require_inventory_writable_on_cursor
        )
        checker(cur, record.inventory_id)
        now = clock_now()
        confirmed = replace(
            record,
            status=LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
            confirmed_at=now,
            confirmed_by_user_id=confirmed_by_user_id or record.confirmed_by_user_id,
            last_error_code=None,
            materialization_owner=None,
            materialization_lease_expires_at=None,
            materialization_next_retry_at=None,
            updated_at=now,
        )
        self._persist(cur, confirmed)
        return confirmed

    def finalize_import_confirmation(
        self,
        *,
        import_id: str,
        clock_now: Callable[[], datetime],
        confirmed_by_user_id: str | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalCsvImport:
        with self._client.begin_transaction() as txn:
            with sql_repository_cursor(self._client, connection=txn.connection) as cur:
                confirmed = self.finalize_import_confirmation_on_cursor(
                    cur,
                    import_id=import_id,
                    clock_now=clock_now,
                    confirmed_by_user_id=confirmed_by_user_id,
                    owner=owner,
                    expected_fencing_version=expected_fencing_version,
                )
            txn.commit()
            return confirmed

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
        code = normalize_stable_error_code(
            error_code, fallback=LOCAL_CSV_MATERIALIZATION_FAILED
        )
        cur.execute(
            f"SELECT {_IMPORT_COLUMNS} FROM local_csv_imports "
            "WITH (UPDLOCK, ROWLOCK) WHERE id = ?",
            ((import_id or "").strip(),),
        )
        header = cur.fetchone()
        if header is None:
            raise LocalCsvImportError(
                LOCAL_CSV_EXPORT_NOT_PREVIEWED, "import not found"
            )
        cur.execute(
            f"SELECT {_ROW_COLUMNS} FROM local_csv_import_rows "
            "WHERE import_id = ? ORDER BY row_number",
            (str(header.id),),
        )
        rows = tuple(_row_from_db(row) for row in cur.fetchall())
        record = _import_from_db(header, rows)
        if record.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
            return record
        assert_owner_may_finalize(
            record,
            owner=owner,
            expected_fencing_version=expected_fencing_version,
        )
        now = clock_now()
        failed = replace(
            record,
            status=(
                LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW
                if requires_review
                else LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED
            ),
            last_error_code=code,
            materialization_owner=None,
            materialization_lease_expires_at=None,
            materialization_next_retry_at=next_retry_at,
            updated_at=now,
        )
        self._persist(cur, failed)
        return failed

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
        with self._client.begin_transaction() as txn:
            with sql_repository_cursor(self._client, connection=txn.connection) as cur:
                failed = self.mark_materialization_failed_on_cursor(
                    cur,
                    import_id=import_id,
                    error_code=error_code,
                    clock_now=clock_now,
                    requires_review=requires_review,
                    next_retry_at=next_retry_at,
                    owner=owner,
                    expected_fencing_version=expected_fencing_version,
                )
            txn.commit()
            return failed

    def list_recovery_candidates(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> tuple[LocalCsvImport, ...]:
        capped = max(1, min(int(limit), 500))
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT TOP ({capped}) {_IMPORT_COLUMNS} FROM local_csv_imports "
                "WHERE (status = ? AND materialization_lease_expires_at <= ?) "
                "OR (status = ? AND (materialization_next_retry_at IS NULL "
                "OR materialization_next_retry_at <= ?)) "
                "ORDER BY updated_at",
                (
                    LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
                    now,
                    LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
                    now,
                ),
            )
            headers = cur.fetchall()
            results: list[LocalCsvImport] = []
            for header in headers:
                cur.execute(
                    f"SELECT {_ROW_COLUMNS} FROM local_csv_import_rows "
                    "WHERE import_id = ? ORDER BY row_number",
                    (str(header.id),),
                )
                rows = tuple(_row_from_db(row) for row in cur.fetchall())
                results.append(_import_from_db(header, rows))
        return tuple(results)

    def save(self, record: LocalCsvImport) -> LocalCsvImport:
        with sql_repository_cursor(self._client) as cur:
            self._persist(cur, record)
        return record

    def _persist(self, cur: SqlCursorLike, record: LocalCsvImport) -> None:
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
            record.source_metadata_json,
            record.last_error_code,
            int(record.materialization_attempts),
            record.materialization_owner,
            record.materialization_lease_expires_at,
            record.materialization_started_at,
            record.materialization_last_attempt_at,
            record.materialization_next_retry_at,
            int(record.fencing_version),
            record.updated_at,
            record.id,
        )
        cur.execute(
            "UPDATE local_csv_imports SET export_id=?, schema_version=?, inventory_id=?, "
            "device_id=?, exported_at=?, status=?, content_hash=?, total_rows=?, valid_rows=?, "
            "rejected_rows=?, duplicate_rows=?, conflict_policy=?, confirmed_at=?, "
            "confirmed_by_user_id=?, source_metadata_json=?, last_error_code=?, "
            "materialization_attempts=?, materialization_owner=?, "
            "materialization_lease_expires_at=?, materialization_started_at=?, "
            "materialization_last_attempt_at=?, materialization_next_retry_at=?, "
            "fencing_version=?, updated_at=? WHERE id=?",
            values,
        )
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO local_csv_imports "
                "(id, export_id, schema_version, inventory_id, device_id, exported_at, status, "
                "content_hash, total_rows, valid_rows, rejected_rows, duplicate_rows, "
                "conflict_policy, confirmed_at, confirmed_by_user_id, source_metadata_json, "
                "last_error_code, materialization_attempts, materialization_owner, "
                "materialization_lease_expires_at, materialization_started_at, "
                "materialization_last_attempt_at, materialization_next_retry_at, "
                "fencing_version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
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
                    record.source_metadata_json,
                    record.last_error_code,
                    int(record.materialization_attempts),
                    record.materialization_owner,
                    record.materialization_lease_expires_at,
                    record.materialization_started_at,
                    record.materialization_last_attempt_at,
                    record.materialization_next_retry_at,
                    int(record.fencing_version),
                    record.created_at,
                    record.updated_at,
                ),
            )
        # Upsert rows in place. Never DELETE+re-INSERT after productive results exist:
        # FK_local_csv_productive_row references import_row_id.
        keep_ids = {row.id for row in record.rows}
        update_sql = (
            "UPDATE local_csv_import_rows SET import_id=?, row_number=?, inventory_id=?, "
            "aisle_id=?, capture_session_id=?, capture_photo_id=?, client_file_id=?, "
            "capture_order=?, captured_at=?, position_code=?, internal_code=?, quantity=?, "
            "quantity_status=?, detection_status=?, detection_source=?, ingestion_source=?, "
            "requires_review=?, error_code=?, notes=?, status=?, validation_errors_json=?, "
            "validation_warnings_json=?, productive_result_id=?, label_id=?, "
            "position_label_id=?, position_payload_raw=? WHERE id=?"
        )
        insert_sql = (
            "INSERT INTO local_csv_import_rows "
            f"({_ROW_COLUMNS}) VALUES ({', '.join('?' for _ in range(27))})"
        )
        update_params: list[tuple[object, ...]] = []
        insert_by_id: dict[str, tuple[object, ...]] = {}
        for row in record.rows:
            update_params.append(
                (
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
                    row.label_id,
                    row.position_label_id,
                    row.position_payload_raw,
                    row.id,
                )
            )
            insert_by_id[row.id] = (
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
                row.label_id,
                row.position_label_id,
                row.position_payload_raw,
            )

        for chunk in chunked(update_params, EXECUTEMANY_IMPORT_ROW_PARAM_SET_CHUNK):
            cursor_executemany(
                cur,
                update_sql,
                chunk,
                operation="local_csv_import_rows.update",
                use_fast_executemany=False,
            )

        cur.execute(
            "SELECT id FROM local_csv_import_rows WHERE import_id = ?",
            (record.id,),
        )
        existing_ids = {str(row.id) for row in cur.fetchall()}
        missing_params = [
            insert_by_id[row_id] for row_id in insert_by_id if row_id not in existing_ids
        ]
        for chunk in chunked(missing_params, EXECUTEMANY_IMPORT_ROW_PARAM_SET_CHUNK):
            cursor_executemany(
                cur,
                insert_sql,
                chunk,
                operation="local_csv_import_rows.insert",
                use_fast_executemany=False,
            )

        if keep_ids:
            placeholders = ", ".join("?" for _ in keep_ids)
            cur.execute(
                "DELETE FROM local_csv_import_rows WHERE import_id = ? AND id NOT IN "
                f"({placeholders}) AND NOT EXISTS ("
                "SELECT 1 FROM local_csv_productive_results p "
                "WHERE p.import_row_id = local_csv_import_rows.id)",
                (record.id, *keep_ids),
            )
        else:
            cur.execute(
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
