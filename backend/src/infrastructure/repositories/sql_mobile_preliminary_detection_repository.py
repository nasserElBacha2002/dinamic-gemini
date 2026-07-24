"""SQL Server repository for mobile_preliminary_detections."""

from __future__ import annotations

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
    )


_SELECT_COLS = """
id, draft_id, inventory_id, aisle_id, asset_id, client_file_id, status,
internal_code, quantity, quantity_status, detected_format, detected_symbology,
candidate_count, parser_version, detector_version, prepared_asset_sha256,
payload_hash, processing_ms, detected_at, received_at, expires_at, validation_status,
validation_error_code, schema_version, created_at, updated_at
"""


class SqlMobilePreliminaryDetectionRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

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
                        validation_status, validation_error_code, schema_version, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?
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
