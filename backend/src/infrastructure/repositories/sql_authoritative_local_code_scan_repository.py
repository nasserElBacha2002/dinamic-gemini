"""SQL Server repository for authoritative_local_code_scan_results."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pyodbc

from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeUniqueViolationError,
    AuthoritativeVersionConflictError,
)
from src.database.sqlserver import SqlServerClient
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _row_to_entity(row) -> AuthoritativeLocalCodeScanResult:
    return AuthoritativeLocalCodeScanResult(
        id=normalize_db_str(getattr(row, "id", None)),
        asset_id=normalize_db_str(getattr(row, "asset_id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        client_file_id=normalize_db_str(getattr(row, "client_file_id", None)),
        result_version=int(getattr(row, "result_version", 1) or 1),
        supersedes_result_id=optional_nonempty_db_str(getattr(row, "supersedes_result_id", None)),
        is_current=bool(getattr(row, "is_current", False)),
        internal_code=normalize_db_str(getattr(row, "internal_code", None)),
        quantity=getattr(row, "quantity", None),
        quantity_status=normalize_db_str(getattr(row, "quantity_status", None)),
        source=normalize_db_str(getattr(row, "source", None)),
        detected_internal_code=optional_nonempty_db_str(
            getattr(row, "detected_internal_code", None)
        ),
        detected_quantity=getattr(row, "detected_quantity", None),
        detected_symbology=optional_nonempty_db_str(getattr(row, "detected_symbology", None)),
        parser_version=normalize_db_str(getattr(row, "parser_version", None)),
        detector_version=normalize_db_str(getattr(row, "detector_version", None)),
        prepared_asset_sha256=normalize_db_str(getattr(row, "prepared_asset_sha256", None)),
        content_hash=normalize_db_str(getattr(row, "content_hash", None)),
        confirmed_by=normalize_db_str(getattr(row, "confirmed_by", None)),
        client_confirmed_at=_ensure_utc(getattr(row, "client_confirmed_at", None)),
        server_confirmed_at=_ensure_utc(getattr(row, "server_confirmed_at", None))
        or datetime.now(timezone.utc),
        server_received_at=_ensure_utc(getattr(row, "server_received_at", None))
        or datetime.now(timezone.utc),
        # Backward-compat alias for callers still reading confirmed_at
        confirmed_at=_ensure_utc(getattr(row, "server_confirmed_at", None))
        or _ensure_utc(getattr(row, "confirmed_at", None))
        or datetime.now(timezone.utc),
        applied_job_id=optional_nonempty_db_str(getattr(row, "applied_job_id", None)),
        applied_at=_ensure_utc(getattr(row, "applied_at", None)),
        row_version=int(getattr(row, "row_version", 1) or 1),
        schema_version=normalize_db_str(getattr(row, "schema_version", None)) or "1",
        created_at=_ensure_utc(getattr(row, "created_at", None)) or datetime.now(timezone.utc),
        updated_at=_ensure_utc(getattr(row, "updated_at", None)) or datetime.now(timezone.utc),
    )


_SELECT_COLS = """
id, asset_id, inventory_id, aisle_id, client_file_id, result_version, supersedes_result_id,
is_current, internal_code, quantity, quantity_status, source, detected_internal_code,
detected_quantity, detected_symbology, parser_version, detector_version, prepared_asset_sha256,
content_hash, confirmed_by, client_confirmed_at, server_confirmed_at, server_received_at,
confirmed_at, applied_job_id, applied_at, row_version, schema_version, created_at, updated_at
"""


class SqlAuthoritativeLocalCodeScanRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_by_id(self, result_id: str) -> AuthoritativeLocalCodeScanResult | None:
        rid = (result_id or "").strip()
        if not rid:
            return None
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM authoritative_local_code_scan_results WHERE id = ?",
                (rid,),
            )
            row = cur.fetchone()
        return _row_to_entity(row) if row else None

    def get_current_for_asset(self, asset_id: str) -> AuthoritativeLocalCodeScanResult | None:
        aid = (asset_id or "").strip()
        if not aid:
            return None
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM authoritative_local_code_scan_results "
                "WHERE asset_id = ? AND is_current = 1",
                (aid,),
            )
            row = cur.fetchone()
        return _row_to_entity(row) if row else None

    def list_current_for_aisle(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[AuthoritativeLocalCodeScanResult]:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM authoritative_local_code_scan_results "
                "WHERE inventory_id = ? AND aisle_id = ? AND is_current = 1 "
                "ORDER BY asset_id, result_version",
                (inventory_id.strip(), aisle_id.strip()),
            )
            rows = cur.fetchall()
        return [_row_to_entity(r) for r in rows]

    def list_current_for_asset_ids(
        self, *, asset_ids: Sequence[str]
    ) -> Sequence[AuthoritativeLocalCodeScanResult]:
        wanted = [a.strip() for a in asset_ids if a and a.strip()]
        if not wanted:
            return []
        placeholders = ",".join("?" for _ in wanted)
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM authoritative_local_code_scan_results "
                f"WHERE is_current = 1 AND asset_id IN ({placeholders})",
                tuple(wanted),
            )
            rows = cur.fetchall()
        return [_row_to_entity(r) for r in rows]

    def max_version_for_asset(self, asset_id: str) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT MAX(result_version) AS max_v FROM authoritative_local_code_scan_results "
                "WHERE asset_id = ?",
                (asset_id.strip(),),
            )
            row = cur.fetchone()
        if not row:
            return 0
        val = getattr(row, "max_v", None)
        if val is None and hasattr(row, "__getitem__"):
            try:
                val = row[0]
            except Exception:
                val = None
        return int(val or 0)

    def create_authoritative_version(
        self,
        *,
        new_result: AuthoritativeLocalCodeScanResult,
        expected_current_id: str | None,
        expected_row_version: int | None,
    ) -> AuthoritativeLocalCodeScanResult:
        """Transactional: lock asset rows, CAS supersede, insert new current."""
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            try:
                cur.execute(
                    f"SELECT {_SELECT_COLS} FROM authoritative_local_code_scan_results "
                    "WITH (UPDLOCK, HOLDLOCK) "
                    "WHERE asset_id = ? AND is_current = 1",
                    (new_result.asset_id,),
                )
                current_row = cur.fetchone()
                current = _row_to_entity(current_row) if current_row else None

                if expected_current_id is None:
                    if current is not None:
                        raise AuthoritativeVersionConflictError("expected_no_current")
                else:
                    if current is None or current.id != expected_current_id:
                        raise AuthoritativeVersionConflictError("current_mismatch")
                    if expected_row_version is None or int(current.row_version) != int(
                        expected_row_version
                    ):
                        raise AuthoritativeVersionConflictError("row_version_mismatch")
                    cur.execute(
                        """
                        UPDATE authoritative_local_code_scan_results
                           SET is_current = 0,
                               row_version = row_version + 1,
                               updated_at = ?
                         WHERE id = ? AND row_version = ? AND is_current = 1
                        """,
                        (new_result.updated_at, current.id, int(expected_row_version)),
                    )
                    if int(cur.rowcount or 0) != 1:
                        raise AuthoritativeVersionConflictError("supersede_cas_failed")

                cur.execute(
                    "SELECT ISNULL(MAX(result_version), 0) AS max_v "
                    "FROM authoritative_local_code_scan_results WHERE asset_id = ?",
                    (new_result.asset_id,),
                )
                max_row = cur.fetchone()
                max_v = int(getattr(max_row, "max_v", None) or 0)
                next_version = max_v + 1

                cur.execute(
                    """
                    INSERT INTO authoritative_local_code_scan_results (
                        id, asset_id, inventory_id, aisle_id, client_file_id, result_version,
                        supersedes_result_id, is_current, internal_code, quantity, quantity_status,
                        source, detected_internal_code, detected_quantity, detected_symbology,
                        parser_version, detector_version, prepared_asset_sha256, content_hash,
                        confirmed_by, client_confirmed_at, server_confirmed_at, server_received_at,
                        confirmed_at, applied_job_id, applied_at, row_version,
                        schema_version, created_at, updated_at
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )
                    """,
                    (
                        new_result.id,
                        new_result.asset_id,
                        new_result.inventory_id,
                        new_result.aisle_id,
                        new_result.client_file_id,
                        next_version,
                        expected_current_id,
                        1,
                        new_result.internal_code,
                        new_result.quantity,
                        new_result.quantity_status,
                        new_result.source,
                        new_result.detected_internal_code,
                        new_result.detected_quantity,
                        new_result.detected_symbology,
                        new_result.parser_version,
                        new_result.detector_version,
                        new_result.prepared_asset_sha256,
                        new_result.content_hash,
                        new_result.confirmed_by,
                        new_result.client_confirmed_at,
                        new_result.server_confirmed_at,
                        new_result.server_received_at,
                        new_result.server_confirmed_at,
                        None,
                        None,
                        1,
                        new_result.schema_version,
                        new_result.created_at,
                        new_result.updated_at,
                    ),
                )
                txn.commit()
            except AuthoritativeVersionConflictError:
                txn.rollback()
                raise
            except pyodbc.IntegrityError as exc:
                txn.rollback()
                raise AuthoritativeUniqueViolationError(str(exc)) from exc
            except Exception:
                txn.rollback()
                raise

        saved = self.get_by_id(new_result.id)
        if saved is None:
            raise RuntimeError(f"authoritative insert missing after commit id={new_result.id}")
        return saved

    def mark_applied_if_version(
        self,
        *,
        result_id: str,
        job_id: str,
        applied_at: datetime,
        expected_row_version: int,
    ) -> AuthoritativeLocalCodeScanResult | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE authoritative_local_code_scan_results
                   SET applied_job_id = ?,
                       applied_at = ?,
                       row_version = row_version + 1,
                       updated_at = ?
                 WHERE id = ? AND row_version = ?
                """,
                (job_id, applied_at, applied_at, result_id.strip(), int(expected_row_version)),
            )
            if int(cur.rowcount or 0) <= 0:
                return None
        return self.get_by_id(result_id)
