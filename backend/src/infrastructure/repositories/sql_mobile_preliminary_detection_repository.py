"""SQL Server repository for mobile_preliminary_detections."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pyodbc

from src.application.ports.mobile_preliminary_detection_repository import (
    PreliminaryUniqueViolationError,
)
from src.database.sqlserver import SqlServerClient
from src.domain.mobile_preliminary_detections.entities import MobilePreliminaryDetection
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _is_draft_id_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    return "uq_mpd_draft_id" in str(exc).lower()


def _is_idempotency_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    return "uq_mpd_client_versions_hash" in str(exc).lower()


def _row_to_entity(row) -> MobilePreliminaryDetection:
    return MobilePreliminaryDetection(
        id=normalize_db_str(getattr(row, "id", None)),
        draft_id=normalize_db_str(getattr(row, "draft_id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        asset_id=normalize_db_str(getattr(row, "asset_id", None)),
        client_file_id=normalize_db_str(getattr(row, "client_file_id", None)),
        status=normalize_db_str(getattr(row, "status", None)),
        internal_code=optional_nonempty_db_str(getattr(row, "internal_code", None)),
        quantity=getattr(row, "quantity", None),
        quantity_status=optional_nonempty_db_str(getattr(row, "quantity_status", None)),
        detected_format=optional_nonempty_db_str(getattr(row, "detected_format", None)),
        detected_symbology=optional_nonempty_db_str(getattr(row, "detected_symbology", None)),
        candidate_count=int(getattr(row, "candidate_count", 0) or 0),
        parser_version=normalize_db_str(getattr(row, "parser_version", None)),
        detector_version=normalize_db_str(getattr(row, "detector_version", None)),
        prepared_asset_sha256=normalize_db_str(getattr(row, "prepared_asset_sha256", None)),
        payload_hash=optional_nonempty_db_str(getattr(row, "payload_hash", None)),
        processing_ms=getattr(row, "processing_ms", None),
        detected_at=_ensure_utc(getattr(row, "detected_at", None)),
        received_at=_ensure_utc(getattr(row, "received_at", None)) or datetime.now(timezone.utc),
        expires_at=_ensure_utc(getattr(row, "expires_at", None)) or datetime.now(timezone.utc),
        validation_status=normalize_db_str(getattr(row, "validation_status", None)),
        validation_error_code=optional_nonempty_db_str(getattr(row, "validation_error_code", None)),
        schema_version=normalize_db_str(getattr(row, "schema_version", None)) or "1",
        created_at=_ensure_utc(getattr(row, "created_at", None)) or datetime.now(timezone.utc),
        updated_at=_ensure_utc(getattr(row, "updated_at", None)) or datetime.now(timezone.utc),
        position_local_recognition_id=optional_nonempty_db_str(
            getattr(row, "position_local_recognition_id", None)
        ),
        position_raw_code=optional_nonempty_db_str(getattr(row, "position_raw_code", None)),
        position_claimed_normalized_code=optional_nonempty_db_str(
            getattr(row, "position_claimed_normalized_code", None)
        ),
        position_claimed_remote_id=optional_nonempty_db_str(
            getattr(row, "position_claimed_remote_id", None)
        ),
        position_claimed_remote_label_id=optional_nonempty_db_str(
            getattr(row, "position_claimed_remote_label_id", None)
        ),
        position_source=optional_nonempty_db_str(getattr(row, "position_source", None)),
        position_profile_id=optional_nonempty_db_str(getattr(row, "position_profile_id", None)),
        position_profile_version=getattr(row, "position_profile_version", None),
        position_client_supplier_id=optional_nonempty_db_str(
            getattr(row, "position_client_supplier_id", None)
        ),
        position_signature_present=getattr(row, "position_signature_present", None),
        position_signature_verification=optional_nonempty_db_str(
            getattr(row, "position_signature_verification", None)
        ),
        position_captured_at=_ensure_utc(getattr(row, "position_captured_at", None)),
        position_result_status=optional_nonempty_db_str(
            getattr(row, "position_result_status", None)
        ),
        position_result_error_code=optional_nonempty_db_str(
            getattr(row, "position_result_error_code", None)
        ),
        position_result_retryable=getattr(row, "position_result_retryable", None),
        position_normalized_code=optional_nonempty_db_str(
            getattr(row, "position_normalized_code", None)
        ),
        position_remote_id=optional_nonempty_db_str(getattr(row, "position_remote_id", None)),
        position_remote_label_id=optional_nonempty_db_str(
            getattr(row, "position_remote_label_id", None)
        ),
        position_validated_at=_ensure_utc(getattr(row, "position_validated_at", None)),
        position_reconciliation_revision=int(
            getattr(row, "position_reconciliation_revision", 0) or 0
        ),
        position_created=getattr(row, "position_created", None),
        position_idempotent_replay=getattr(row, "position_idempotent_replay", None),
        position_materialization_request_id=optional_nonempty_db_str(
            getattr(row, "position_materialization_request_id", None)
        ),
    )


_SELECT_COLS = """
id, draft_id, inventory_id, aisle_id, asset_id, client_file_id, status,
internal_code, quantity, quantity_status, detected_format, detected_symbology,
candidate_count, parser_version, detector_version, prepared_asset_sha256,
payload_hash, processing_ms, detected_at, received_at, expires_at, validation_status,
validation_error_code, schema_version, created_at, updated_at,
position_local_recognition_id, position_raw_code, position_claimed_normalized_code,
position_claimed_remote_id, position_claimed_remote_label_id, position_source,
position_profile_id, position_profile_version, position_client_supplier_id,
position_signature_present, position_signature_verification, position_captured_at,
position_result_status, position_result_error_code, position_result_retryable,
position_normalized_code, position_remote_id, position_remote_label_id,
position_validated_at, position_reconciliation_revision,
position_created, position_idempotent_replay, position_materialization_request_id
"""


class SqlMobilePreliminaryDetectionRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def exists_by_materialization_request_id(self, request_id: str) -> bool:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT TOP (1) 1
                FROM dbo.mobile_preliminary_detections
                WHERE position_materialization_request_id = ?
                """,
                (request_id,),
            )
            return cur.fetchone() is not None

    def get_by_draft_id(self, draft_id: str) -> MobilePreliminaryDetection | None:
        did = (draft_id or "").strip()
        if not did:
            return None
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM mobile_preliminary_detections WHERE draft_id = ?",
                (did,),
            )
            row = cur.fetchone()
        return _row_to_entity(row) if row else None

    def get_by_idempotency_key(
        self,
        *,
        client_file_id: str,
        detector_version: str,
        parser_version: str,
        prepared_asset_sha256: str,
    ) -> MobilePreliminaryDetection | None:
        key = (
            (client_file_id or "").strip(),
            (detector_version or "").strip(),
            (parser_version or "").strip(),
            (prepared_asset_sha256 or "").strip(),
        )
        if not all(key):
            return None
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_COLS} FROM mobile_preliminary_detections
                WHERE client_file_id = ?
                  AND detector_version = ?
                  AND parser_version = ?
                  AND prepared_asset_sha256 = ?
                """,
                key,
            )
            row = cur.fetchone()
        return _row_to_entity(row) if row else None

    def insert(self, row: MobilePreliminaryDetection) -> MobilePreliminaryDetection:
        try:
            with self._client.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mobile_preliminary_detections (
                        id, draft_id, inventory_id, aisle_id, asset_id, client_file_id, status,
                        internal_code, quantity, quantity_status, detected_format, detected_symbology,
                        candidate_count, parser_version, detector_version, prepared_asset_sha256,
                        payload_hash, processing_ms, detected_at, received_at, expires_at,
                        validation_status, validation_error_code, schema_version, created_at, updated_at,
                        position_local_recognition_id, position_raw_code,
                        position_claimed_normalized_code, position_claimed_remote_id,
                        position_claimed_remote_label_id, position_source, position_profile_id,
                        position_profile_version, position_client_supplier_id,
                        position_signature_present, position_signature_verification,
                        position_captured_at, position_result_status, position_result_error_code,
                        position_result_retryable, position_normalized_code, position_remote_id,
                        position_remote_label_id, position_validated_at,
                        position_reconciliation_revision, position_created,
                        position_idempotent_replay, position_materialization_request_id
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        row.id,
                        row.draft_id,
                        row.inventory_id,
                        row.aisle_id,
                        row.asset_id,
                        row.client_file_id,
                        row.status,
                        row.internal_code,
                        row.quantity,
                        row.quantity_status,
                        row.detected_format,
                        row.detected_symbology,
                        row.candidate_count,
                        row.parser_version,
                        row.detector_version,
                        row.prepared_asset_sha256,
                        row.payload_hash,
                        row.processing_ms,
                        row.detected_at,
                        row.received_at,
                        row.expires_at,
                        row.validation_status,
                        row.validation_error_code,
                        row.schema_version,
                        row.created_at,
                        row.updated_at,
                        row.position_local_recognition_id,
                        row.position_raw_code,
                        row.position_claimed_normalized_code,
                        row.position_claimed_remote_id,
                        row.position_claimed_remote_label_id,
                        row.position_source,
                        row.position_profile_id,
                        row.position_profile_version,
                        row.position_client_supplier_id,
                        row.position_signature_present,
                        row.position_signature_verification,
                        row.position_captured_at,
                        row.position_result_status,
                        row.position_result_error_code,
                        row.position_result_retryable,
                        row.position_normalized_code,
                        row.position_remote_id,
                        row.position_remote_label_id,
                        row.position_validated_at,
                        row.position_reconciliation_revision,
                        row.position_created,
                        row.position_idempotent_replay,
                        row.position_materialization_request_id,
                    ),
                )
        except pyodbc.IntegrityError as exc:
            if _is_draft_id_unique_violation(exc):
                raise PreliminaryUniqueViolationError("draft_id") from exc
            if _is_idempotency_unique_violation(exc):
                raise PreliminaryUniqueViolationError("idempotency_key") from exc
            raise
        return row

    def delete_expired(self, *, now: datetime, limit: int = 500) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                """
                DELETE TOP (?) FROM mobile_preliminary_detections
                WHERE expires_at <= ?
                """,
                (int(limit), now),
            )
            return int(cur.rowcount or 0)

    def list_validated_by_aisle(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        limit: int = 500,
    ) -> list[MobilePreliminaryDetection]:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT TOP (?) {_SELECT_COLS}
                FROM mobile_preliminary_detections
                WHERE inventory_id = ? AND aisle_id = ? AND validation_status = 'VALIDATED'
                ORDER BY received_at ASC
                """,
                (int(limit), inventory_id.strip(), aisle_id.strip()),
            )
            return [_row_to_entity(row) for row in cur.fetchall()]

    def list_validated_by_asset_ids(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        asset_ids: Sequence[str],
        limit: int = 500,
    ) -> list[MobilePreliminaryDetection]:
        ids = [a.strip() for a in asset_ids if a and str(a).strip()]
        if not ids:
            return []
        # Cap IN-list size for SQL Server parameter limits
        ids = ids[: min(len(ids), int(limit), 500)]
        placeholders = ",".join("?" for _ in ids)
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT TOP (?) {_SELECT_COLS}
                FROM mobile_preliminary_detections
                WHERE inventory_id = ? AND aisle_id = ?
                  AND validation_status = 'VALIDATED'
                  AND asset_id IN ({placeholders})
                ORDER BY received_at ASC
                """,
                (int(limit), inventory_id.strip(), aisle_id.strip(), *ids),
            )
            return [_row_to_entity(row) for row in cur.fetchall()]
