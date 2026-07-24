"""SQL Server repository for preliminary_detection_reconciliations (Phase 5 corrections)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pyodbc

from src.application.ports.preliminary_detection_reconciliation_repository import (
    ReconciliationRowVersionConflictError,
    ReconciliationUniqueViolationError,
)
from src.application.services.preliminary_detection_compare import OUTCOME_NOT_COMPARABLE
from src.database.sqlserver import SqlServerClient
from src.domain.preliminary_detection_reconciliations.entities import (
    PreliminaryDetectionReconciliation,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


_SELECT_COLS = """
id, preliminary_detection_id, asset_id, remote_result_id, job_id, inventory_id, aisle_id,
client_file_id, local_status, local_internal_code, local_quantity, remote_status,
remote_internal_code, remote_quantity, outcome, not_comparable_reason,
local_parser_version, local_detector_version, remote_pipeline_version,
local_detected_at, remote_completed_at, compared_at, comparison_version,
reconciliation_status, created_at, updated_at, remote_result_fingerprint, revision,
supersedes_id, row_version, attempt_count, next_retry_at, lease_token, lease_expires_at,
last_error_code, app_version, device_model, preparation_profile, expires_at
"""


def _row_to_entity(row) -> PreliminaryDetectionReconciliation:
    return PreliminaryDetectionReconciliation(
        id=normalize_db_str(getattr(row, "id", None)),
        preliminary_detection_id=normalize_db_str(getattr(row, "preliminary_detection_id", None)),
        asset_id=normalize_db_str(getattr(row, "asset_id", None)),
        remote_result_id=optional_nonempty_db_str(getattr(row, "remote_result_id", None)),
        job_id=normalize_db_str(getattr(row, "job_id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        client_file_id=normalize_db_str(getattr(row, "client_file_id", None)),
        local_status=normalize_db_str(getattr(row, "local_status", None)),
        local_internal_code=optional_nonempty_db_str(getattr(row, "local_internal_code", None)),
        local_quantity=getattr(row, "local_quantity", None),
        remote_status=optional_nonempty_db_str(getattr(row, "remote_status", None)),
        remote_internal_code=optional_nonempty_db_str(getattr(row, "remote_internal_code", None)),
        remote_quantity=getattr(row, "remote_quantity", None),
        outcome=normalize_db_str(getattr(row, "outcome", None)) or "NOT_COMPARABLE",
        not_comparable_reason=optional_nonempty_db_str(getattr(row, "not_comparable_reason", None)),
        local_parser_version=optional_nonempty_db_str(getattr(row, "local_parser_version", None)),
        local_detector_version=optional_nonempty_db_str(
            getattr(row, "local_detector_version", None)
        ),
        remote_pipeline_version=optional_nonempty_db_str(
            getattr(row, "remote_pipeline_version", None)
        ),
        local_detected_at=_ensure_utc(getattr(row, "local_detected_at", None)),
        remote_completed_at=_ensure_utc(getattr(row, "remote_completed_at", None)),
        compared_at=_ensure_utc(getattr(row, "compared_at", None)) or datetime.now(timezone.utc),
        comparison_version=normalize_db_str(getattr(row, "comparison_version", None)) or "1",
        reconciliation_status=normalize_db_str(getattr(row, "reconciliation_status", None)),
        created_at=_ensure_utc(getattr(row, "created_at", None)) or datetime.now(timezone.utc),
        updated_at=_ensure_utc(getattr(row, "updated_at", None)) or datetime.now(timezone.utc),
        remote_result_fingerprint=normalize_db_str(
            getattr(row, "remote_result_fingerprint", None)
        )
        or "PENDING",
        revision=int(getattr(row, "revision", 1) or 1),
        supersedes_id=optional_nonempty_db_str(getattr(row, "supersedes_id", None)),
        row_version=int(getattr(row, "row_version", 1) or 1),
        attempt_count=int(getattr(row, "attempt_count", 0) or 0),
        next_retry_at=_ensure_utc(getattr(row, "next_retry_at", None)),
        lease_token=optional_nonempty_db_str(getattr(row, "lease_token", None)),
        lease_expires_at=_ensure_utc(getattr(row, "lease_expires_at", None)),
        last_error_code=optional_nonempty_db_str(getattr(row, "last_error_code", None)),
        app_version=optional_nonempty_db_str(getattr(row, "app_version", None)),
        device_model=optional_nonempty_db_str(getattr(row, "device_model", None)),
        preparation_profile=optional_nonempty_db_str(getattr(row, "preparation_profile", None)),
        expires_at=_ensure_utc(getattr(row, "expires_at", None)),
    )


def _insert_params(row: PreliminaryDetectionReconciliation) -> tuple:
    return (
        row.id,
        row.preliminary_detection_id,
        row.asset_id,
        row.remote_result_id,
        row.job_id,
        row.inventory_id,
        row.aisle_id,
        row.client_file_id,
        row.local_status,
        row.local_internal_code,
        row.local_quantity,
        row.remote_status,
        row.remote_internal_code,
        row.remote_quantity,
        row.outcome,
        row.not_comparable_reason,
        row.local_parser_version,
        row.local_detector_version,
        row.remote_pipeline_version,
        row.local_detected_at,
        row.remote_completed_at,
        row.compared_at,
        row.comparison_version,
        row.reconciliation_status,
        row.created_at,
        row.updated_at,
        row.remote_result_fingerprint,
        row.revision,
        row.supersedes_id,
        row.row_version,
        row.attempt_count,
        row.next_retry_at,
        row.lease_token,
        row.lease_expires_at,
        row.last_error_code,
        row.app_version,
        row.device_model,
        row.preparation_profile,
        row.expires_at,
    )


class SqlPreliminaryDetectionReconciliationRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_by_id(self, reconciliation_id: str) -> PreliminaryDetectionReconciliation | None:
        rid = (reconciliation_id or "").strip()
        if not rid:
            return None
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM preliminary_detection_reconciliations WHERE id = ?",
                (rid,),
            )
            row = cur.fetchone()
            return _row_to_entity(row) if row else None

    def get_by_identity(
        self,
        *,
        preliminary_detection_id: str,
        comparison_version: str,
        job_id: str,
    ) -> PreliminaryDetectionReconciliation | None:
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM preliminary_detection_reconciliations "
                "WHERE preliminary_detection_id = ? AND comparison_version = ? AND job_id = ?",
                (preliminary_detection_id.strip(), comparison_version.strip(), job_id.strip()),
            )
            row = cur.fetchone()
            return _row_to_entity(row) if row else None

    def insert(
        self, row: PreliminaryDetectionReconciliation
    ) -> PreliminaryDetectionReconciliation:
        try:
            with self._client.connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO preliminary_detection_reconciliations (
                        id, preliminary_detection_id, asset_id, remote_result_id, job_id,
                        inventory_id, aisle_id, client_file_id, local_status,
                        local_internal_code, local_quantity, remote_status,
                        remote_internal_code, remote_quantity, outcome, not_comparable_reason,
                        local_parser_version, local_detector_version, remote_pipeline_version,
                        local_detected_at, remote_completed_at, compared_at, comparison_version,
                        reconciliation_status, created_at, updated_at, remote_result_fingerprint,
                        revision, supersedes_id, row_version, attempt_count, next_retry_at,
                        lease_token, lease_expires_at, last_error_code, app_version, device_model,
                        preparation_profile, expires_at
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )
                    """,
                    _insert_params(row),
                )
                conn.commit()
        except pyodbc.IntegrityError as exc:
            if "uq_pdr_preliminary_version_job" in str(exc).lower():
                raise ReconciliationUniqueViolationError() from exc
            raise
        return row

    def update_if_version(
        self, row: PreliminaryDetectionReconciliation, *, expected_version: int
    ) -> PreliminaryDetectionReconciliation:
        new_version = expected_version + 1
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE preliminary_detection_reconciliations SET
                    remote_result_id = ?, remote_result_fingerprint = ?,
                    local_status = ?, local_internal_code = ?, local_quantity = ?,
                    remote_status = ?, remote_internal_code = ?, remote_quantity = ?,
                    outcome = ?, not_comparable_reason = ?,
                    local_parser_version = ?, local_detector_version = ?,
                    remote_pipeline_version = ?, local_detected_at = ?,
                    remote_completed_at = ?, compared_at = ?,
                    reconciliation_status = ?, attempt_count = ?, next_retry_at = ?,
                    lease_token = ?, lease_expires_at = ?, last_error_code = ?,
                    revision = ?, supersedes_id = ?, app_version = ?, device_model = ?,
                    preparation_profile = ?, expires_at = ?,
                    row_version = ?, updated_at = ?
                WHERE id = ? AND row_version = ?
                """,
                (
                    row.remote_result_id,
                    row.remote_result_fingerprint,
                    row.local_status,
                    row.local_internal_code,
                    row.local_quantity,
                    row.remote_status,
                    row.remote_internal_code,
                    row.remote_quantity,
                    row.outcome,
                    row.not_comparable_reason,
                    row.local_parser_version,
                    row.local_detector_version,
                    row.remote_pipeline_version,
                    row.local_detected_at,
                    row.remote_completed_at,
                    row.compared_at,
                    row.reconciliation_status,
                    row.attempt_count,
                    row.next_retry_at,
                    row.lease_token,
                    row.lease_expires_at,
                    row.last_error_code,
                    row.revision,
                    row.supersedes_id,
                    row.app_version,
                    row.device_model,
                    row.preparation_profile,
                    row.expires_at,
                    new_version,
                    row.updated_at,
                    row.id,
                    expected_version,
                ),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise ReconciliationRowVersionConflictError()
            conn.commit()
        return PreliminaryDetectionReconciliation(**{**row.__dict__, "row_version": new_version})

    def list_by_aisle(self, **kwargs) -> Sequence[PreliminaryDetectionReconciliation]:
        limit = int(kwargs.pop("limit", 200))
        offset = int(kwargs.pop("offset", 0))
        where, params = self._where(**kwargs)
        sql = (
            f"SELECT {_SELECT_COLS} FROM preliminary_detection_reconciliations "
            f"WHERE {where} ORDER BY compared_at DESC "
            f"OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        )
        params.extend([offset, limit])
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            return [_row_to_entity(r) for r in cur.fetchall()]

    def count_by_aisle(self, **kwargs) -> int:
        where, params = self._where(**kwargs)
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT COUNT(1) AS c FROM preliminary_detection_reconciliations WHERE {where}",
                tuple(params),
            )
            row = cur.fetchone()
            return int(getattr(row, "c", 0) or 0)

    def aggregate_metrics(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str | None = None,
        parser_version: str | None = None,
        detector_version: str | None = None,
    ) -> dict[str, int]:
        clauses = ["inventory_id = ?", "aisle_id = ?"]
        params: list = [inventory_id, aisle_id]
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if parser_version:
            clauses.append("local_parser_version = ?")
            params.append(parser_version)
        if detector_version:
            clauses.append("local_detector_version = ?")
            params.append(detector_version)
        where = " AND ".join(clauses)
        sql = f"""
        SELECT
          SUM(CASE WHEN reconciliation_status IN ('COMPLETED','NOT_COMPARABLE','FAILED_TERMINAL')
                   THEN 1 ELSE 0 END) AS total_reconciled,
          SUM(CASE WHEN reconciliation_status IN ('PENDING','RUNNING','RETRY_SCHEDULED')
                   THEN 1 ELSE 0 END) AS total_pending,
          SUM(CASE WHEN reconciliation_status IN ('COMPLETED','NOT_COMPARABLE','FAILED_TERMINAL')
                    AND outcome = 'NOT_COMPARABLE' THEN 1 ELSE 0 END) AS total_not_comparable,
          SUM(CASE WHEN reconciliation_status = 'COMPLETED'
                    AND outcome <> 'NOT_COMPARABLE' THEN 1 ELSE 0 END) AS mapping_comparable,
          SUM(CASE WHEN reconciliation_status = 'COMPLETED'
                    AND outcome IN (
                      'MATCH_CODE_AND_QUANTITY','MATCH_CODE_BOTH_QUANTITY_MISSING',
                      'MATCH_CODE_LOCAL_QUANTITY_MISSING','MATCH_CODE_REMOTE_QUANTITY_MISSING',
                      'MATCH_CODE_QUANTITY_DIFFERENT','CODE_MISMATCH','LOCAL_ONLY','REMOTE_ONLY'
                    ) THEN 1 ELSE 0 END) AS code_comparable,
          SUM(CASE WHEN outcome IN (
                      'MATCH_CODE_AND_QUANTITY','MATCH_CODE_BOTH_QUANTITY_MISSING',
                      'MATCH_CODE_LOCAL_QUANTITY_MISSING','MATCH_CODE_REMOTE_QUANTITY_MISSING',
                      'MATCH_CODE_QUANTITY_DIFFERENT'
                    ) THEN 1 ELSE 0 END) AS quantity_comparable,
          SUM(CASE WHEN outcome IN (
                      'MATCH_CODE_AND_QUANTITY','MATCH_CODE_BOTH_QUANTITY_MISSING',
                      'MATCH_CODE_LOCAL_QUANTITY_MISSING','MATCH_CODE_REMOTE_QUANTITY_MISSING',
                      'MATCH_CODE_QUANTITY_DIFFERENT'
                    ) THEN 1 ELSE 0 END) AS code_match_count,
          SUM(CASE WHEN outcome = 'CODE_MISMATCH' THEN 1 ELSE 0 END) AS code_mismatch_count,
          SUM(CASE WHEN outcome IN ('MATCH_CODE_AND_QUANTITY','MATCH_CODE_BOTH_QUANTITY_MISSING')
                   THEN 1 ELSE 0 END) AS quantity_match_count,
          SUM(CASE WHEN outcome = 'MATCH_CODE_QUANTITY_DIFFERENT' THEN 1 ELSE 0 END)
              AS quantity_mismatch_count,
          SUM(CASE WHEN outcome = 'LOCAL_ONLY' THEN 1 ELSE 0 END) AS local_only_count,
          SUM(CASE WHEN outcome = 'REMOTE_ONLY' THEN 1 ELSE 0 END) AS remote_only_count,
          SUM(CASE WHEN outcome IN ('LOCAL_AMBIGUOUS','REMOTE_AMBIGUOUS','BOTH_AMBIGUOUS')
                   THEN 1 ELSE 0 END) AS ambiguous_count,
          SUM(CASE WHEN outcome = 'BOTH_UNRESOLVED' THEN 1 ELSE 0 END) AS both_unresolved_count
        FROM preliminary_detection_reconciliations
        WHERE {where}
        """
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
            if row is None:
                return {}
            keys = [
                "total_reconciled",
                "total_pending",
                "total_not_comparable",
                "mapping_comparable",
                "code_comparable",
                "quantity_comparable",
                "code_match_count",
                "code_mismatch_count",
                "quantity_match_count",
                "quantity_mismatch_count",
                "local_only_count",
                "remote_only_count",
                "ambiguous_count",
                "both_unresolved_count",
            ]
            return {k: int(getattr(row, k, 0) or 0) for k in keys}

    def claim_due(
        self,
        *,
        lease_token: str,
        lease_expires_at: datetime,
        now: datetime,
        limit: int = 50,
    ) -> Sequence[PreliminaryDetectionReconciliation]:
        claimed: list[PreliminaryDetectionReconciliation] = []
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                ;WITH due AS (
                    SELECT TOP (?) id
                    FROM preliminary_detection_reconciliations WITH (UPDLOCK, READPAST, ROWLOCK)
                    WHERE reconciliation_status = 'PENDING'
                       OR (reconciliation_status = 'RETRY_SCHEDULED'
                           AND (next_retry_at IS NULL OR next_retry_at <= ?))
                       OR (reconciliation_status = 'RUNNING'
                           AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?)
                    ORDER BY created_at ASC
                )
                UPDATE p SET
                    reconciliation_status = 'RUNNING',
                    lease_token = ?,
                    lease_expires_at = ?,
                    attempt_count = attempt_count + 1,
                    row_version = row_version + 1,
                    updated_at = ?
                OUTPUT inserted.id
                FROM preliminary_detection_reconciliations p
                INNER JOIN due ON due.id = p.id
                """,
                (int(limit), now, now, lease_token, lease_expires_at, now),
            )
            ids = [normalize_db_str(getattr(r, "id", None)) for r in cur.fetchall()]
            conn.commit()
        for rid in ids:
            row = self.get_by_id(rid)
            if row:
                claimed.append(row)
        return claimed

    def release_expired_leases(self, *, now: datetime) -> int:
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE preliminary_detection_reconciliations
                SET reconciliation_status = CASE WHEN attempt_count > 0
                                                 THEN 'RETRY_SCHEDULED' ELSE 'PENDING' END,
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    next_retry_at = ?,
                    row_version = row_version + 1,
                    updated_at = ?
                WHERE reconciliation_status = 'RUNNING'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= ?
                """,
                (now, now, now),
            )
            n = int(cur.rowcount or 0)
            conn.commit()
            return n

    def list_by_preliminary_ids(
        self, preliminary_ids: Sequence[str]
    ) -> Sequence[PreliminaryDetectionReconciliation]:
        ids = [p.strip() for p in preliminary_ids if p and str(p).strip()][:500]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM preliminary_detection_reconciliations "
                f"WHERE preliminary_detection_id IN ({placeholders})",
                tuple(ids),
            )
            return [_row_to_entity(r) for r in cur.fetchall()]

    def delete_expired(self, *, now: datetime, limit: int = 500) -> int:
        with self._client.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                DELETE TOP (?) FROM preliminary_detection_reconciliations
                WHERE expires_at IS NOT NULL AND expires_at <= ?
                """,
                (int(limit), now),
            )
            n = int(cur.rowcount or 0)
            conn.commit()
            return n

    def _where(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str | None = None,
        preliminary_detection_id: str | None = None,
        comparison_version: str | None = None,
        outcome: str | None = None,
        asset_id: str | None = None,
        client_file_id: str | None = None,
        parser_version: str | None = None,
        detector_version: str | None = None,
        comparable_only: bool | None = None,
        compared_after: datetime | None = None,
        compared_before: datetime | None = None,
    ) -> tuple[str, list]:
        clauses = ["inventory_id = ?", "aisle_id = ?"]
        params: list = [inventory_id, aisle_id]
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if preliminary_detection_id:
            clauses.append("preliminary_detection_id = ?")
            params.append(preliminary_detection_id)
        if comparison_version:
            clauses.append("comparison_version = ?")
            params.append(comparison_version)
        if outcome:
            clauses.append("outcome = ?")
            params.append(outcome)
        if asset_id:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if client_file_id:
            clauses.append("client_file_id = ?")
            params.append(client_file_id)
        if parser_version:
            clauses.append("local_parser_version = ?")
            params.append(parser_version)
        if detector_version:
            clauses.append("local_detector_version = ?")
            params.append(detector_version)
        if comparable_only is True:
            clauses.append("outcome <> ?")
            params.append(OUTCOME_NOT_COMPARABLE)
        elif comparable_only is False:
            clauses.append("outcome = ?")
            params.append(OUTCOME_NOT_COMPARABLE)
        if compared_after:
            clauses.append("compared_at >= ?")
            params.append(compared_after)
        if compared_before:
            clauses.append("compared_at <= ?")
            params.append(compared_before)
        return " AND ".join(clauses), params
