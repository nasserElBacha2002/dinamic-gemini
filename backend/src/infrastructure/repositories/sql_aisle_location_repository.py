"""SQL Server aisle location + positioning label repositories."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import pyodbc

from src.application.errors import IdempotencyKeyReusedError
from src.application.ports.aisle_location_repository import (
    AisleLocationLabelRepository,
    AisleLocationRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.aisle_location.entities import AisleLocation, AisleLocationStatus
from src.domain.aisle_location.label_entities import (
    AisleLocationLabel,
    AisleLocationLabelStatus,
    PositioningLabelSignatureStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str


def _is_label_client_idempotency_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    return "uq_aisle_location_labels_client_idempotency" in str(exc).lower()


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _row_to_location(row) -> AisleLocation:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "ACTIVE"
    try:
        status = AisleLocationStatus(status_raw)
    except ValueError:
        status = AisleLocationStatus.ACTIVE
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise ValueError("aisle_locations row missing timestamps")
    return AisleLocation(
        id=normalize_db_str(getattr(row, "id", None)),
        client_id=normalize_db_str(getattr(row, "client_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        code=normalize_db_str(getattr(row, "code", None)),
        normalized_code=normalize_db_str(getattr(row, "normalized_code", None)),
        status=status,
        created_at=created,
        updated_at=updated,
        display_name=optional_nonempty_db_str(getattr(row, "display_name", None)),
        description=optional_nonempty_db_str(getattr(row, "description", None)),
        created_by=optional_nonempty_db_str(getattr(row, "created_by", None)),
    )


def _parse_payload(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("payload_json must be an object")
    return parsed


def _row_to_label(row) -> AisleLocationLabel:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "ACTIVE"
    try:
        status = AisleLocationLabelStatus(status_raw)
    except ValueError:
        status = AisleLocationLabelStatus.ACTIVE
    sig_raw = normalize_db_str(getattr(row, "signature_status", None)) or "NOT_IMPLEMENTED"
    try:
        signature_status = PositioningLabelSignatureStatus(sig_raw)
    except ValueError:
        signature_status = PositioningLabelSignatureStatus.NOT_IMPLEMENTED
    generated = _ensure_utc(getattr(row, "generated_at", None))
    if generated is None:
        raise ValueError("aisle_location_labels row missing generated_at")
    return AisleLocationLabel(
        id=normalize_db_str(getattr(row, "id", None)),
        client_id=normalize_db_str(getattr(row, "client_id", None)),
        location_id=normalize_db_str(getattr(row, "location_id", None)),
        public_identifier=normalize_db_str(getattr(row, "public_identifier", None)),
        payload_version=int(getattr(row, "payload_version", 1) or 1),
        marker_version=int(getattr(row, "marker_version", 1) or 1),
        template_version=int(getattr(row, "template_version", 1) or 1),
        status=status,
        payload=_parse_payload(getattr(row, "payload_json", None)),
        generated_at=generated,
        payload_hash=optional_nonempty_db_str(getattr(row, "payload_hash", None)),
        signature_status=signature_status,
        generated_by=optional_nonempty_db_str(getattr(row, "generated_by", None)),
        invalidated_at=_ensure_utc(getattr(row, "invalidated_at", None)),
        invalidation_reason=optional_nonempty_db_str(getattr(row, "invalidation_reason", None)),
        replaced_by_label_id=optional_nonempty_db_str(
            getattr(row, "replaced_by_label_id", None)
        ),
        idempotency_key=optional_nonempty_db_str(getattr(row, "idempotency_key", None)),
        idempotency_request_hash=optional_nonempty_db_str(
            getattr(row, "idempotency_request_hash", None)
        ),
    )


_LOC_SELECT = """
SELECT id, client_id, aisle_id, code, normalized_code, display_name, description,
       status, created_by, created_at, updated_at
FROM aisle_locations
"""

_LABEL_SELECT = """
SELECT id, client_id, location_id, public_identifier, payload_version, marker_version,
       template_version, status, payload_json, payload_hash, signature_status,
       generated_by, generated_at, invalidated_at, invalidation_reason, replaced_by_label_id,
       idempotency_key, idempotency_request_hash
FROM aisle_location_labels
"""


class SqlAisleLocationRepository(AisleLocationRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, location: AisleLocation) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE aisle_locations
                SET client_id = ?, aisle_id = ?, code = ?, normalized_code = ?,
                    display_name = ?, description = ?, status = ?, created_by = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    location.client_id,
                    location.aisle_id,
                    location.code,
                    location.normalized_code,
                    location.display_name,
                    location.description,
                    location.status.value,
                    location.created_by,
                    _ensure_utc(location.updated_at),
                    location.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO aisle_locations (
                        id, client_id, aisle_id, code, normalized_code, display_name,
                        description, status, created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        location.id,
                        location.client_id,
                        location.aisle_id,
                        location.code,
                        location.normalized_code,
                        location.display_name,
                        location.description,
                        location.status.value,
                        location.created_by,
                        _ensure_utc(location.created_at),
                        _ensure_utc(location.updated_at),
                    ),
                )

    def get_by_id(self, location_id: str) -> AisleLocation | None:
        with self._client.cursor() as cur:
            cur.execute(_LOC_SELECT + " WHERE id = ?", (location_id,))
            row = cur.fetchone()
        return _row_to_location(row) if row else None

    def get_active_by_normalized_code(
        self,
        *,
        client_id: str,
        aisle_id: str,
        normalized_code: str,
    ) -> AisleLocation | None:
        with self._client.cursor() as cur:
            cur.execute(
                _LOC_SELECT
                + " WHERE client_id = ? AND aisle_id = ? AND normalized_code = ?"
                + " AND status = 'ACTIVE'",
                (client_id, aisle_id, normalized_code),
            )
            row = cur.fetchone()
        return _row_to_location(row) if row else None

    def list_by_aisle(
        self,
        aisle_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AisleLocation]:
        clauses = ["aisle_id = ?"]
        params: list[Any] = [aisle_id]
        if status:
            clauses.append("status = ?")
            params.append(status.upper())
        if search and search.strip():
            clauses.append(
                "(LOWER(code) LIKE ? OR LOWER(ISNULL(display_name,'')) LIKE ?"
                " OR LOWER(ISNULL(description,'')) LIKE ?)"
            )
            like = f"%{search.strip().lower()}%"
            params.extend([like, like, like])
        where = " AND ".join(clauses)
        params.extend([int(offset), int(limit)])
        sql = (
            _LOC_SELECT
            + f" WHERE {where} ORDER BY normalized_code ASC, id ASC"
            + " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        )
        with self._client.cursor() as cur:
            cur.execute(sql, params)  # nosec B608
            rows = cur.fetchall()
        return [_row_to_location(r) for r in rows]

    def count_by_aisle(
        self,
        aisle_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
    ) -> int:
        clauses = ["aisle_id = ?"]
        params: list[Any] = [aisle_id]
        if status:
            clauses.append("status = ?")
            params.append(status.upper())
        if search and search.strip():
            clauses.append(
                "(LOWER(code) LIKE ? OR LOWER(ISNULL(display_name,'')) LIKE ?"
                " OR LOWER(ISNULL(description,'')) LIKE ?)"
            )
            like = f"%{search.strip().lower()}%"
            params.extend([like, like, like])
        where = " AND ".join(clauses)
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM aisle_locations WHERE {where}",  # nosec B608
                params,
            )
            row = cur.fetchone()
        return int(getattr(row, "cnt", 0) or 0)


class SqlAisleLocationLabelRepository(AisleLocationLabelRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, label: AisleLocationLabel) -> None:
        payload_str = json.dumps(label.payload, ensure_ascii=False, sort_keys=True)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE aisle_location_labels
                SET client_id = ?, location_id = ?, public_identifier = ?,
                    payload_version = ?, marker_version = ?, template_version = ?,
                    status = ?, payload_json = ?, payload_hash = ?, signature_status = ?,
                    generated_by = ?, invalidated_at = ?, invalidation_reason = ?,
                    replaced_by_label_id = ?, idempotency_key = ?, idempotency_request_hash = ?
                WHERE id = ?
                """,
                (
                    label.client_id,
                    label.location_id,
                    label.public_identifier,
                    label.payload_version,
                    label.marker_version,
                    label.template_version,
                    label.status.value,
                    payload_str,
                    label.payload_hash,
                    label.signature_status.value,
                    label.generated_by,
                    _ensure_utc(label.invalidated_at),
                    label.invalidation_reason,
                    label.replaced_by_label_id,
                    label.idempotency_key,
                    label.idempotency_request_hash,
                    label.id,
                ),
            )
            if cur.rowcount == 0:
                try:
                    cur.execute(
                        """
                        INSERT INTO aisle_location_labels (
                            id, client_id, location_id, public_identifier, payload_version,
                            marker_version, template_version, status, payload_json, payload_hash,
                            signature_status, generated_by, generated_at, invalidated_at,
                            invalidation_reason, replaced_by_label_id,
                            idempotency_key, idempotency_request_hash
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            label.id,
                            label.client_id,
                            label.location_id,
                            label.public_identifier,
                            label.payload_version,
                            label.marker_version,
                            label.template_version,
                            label.status.value,
                            payload_str,
                            label.payload_hash,
                            label.signature_status.value,
                            label.generated_by,
                            _ensure_utc(label.generated_at),
                            _ensure_utc(label.invalidated_at),
                            label.invalidation_reason,
                            label.replaced_by_label_id,
                            label.idempotency_key,
                            label.idempotency_request_hash,
                        ),
                    )
                except pyodbc.IntegrityError as exc:
                    if _is_label_client_idempotency_unique_violation(exc):
                        raise IdempotencyKeyReusedError(
                            "IDEMPOTENCY_KEY_REUSED: key already registered"
                        ) from exc
                    raise

    def get_by_id(self, label_id: str) -> AisleLocationLabel | None:
        with self._client.cursor() as cur:
            cur.execute(_LABEL_SELECT + " WHERE id = ?", (label_id,))
            row = cur.fetchone()
        return _row_to_label(row) if row else None

    def get_by_public_identifier(self, public_identifier: str) -> AisleLocationLabel | None:
        with self._client.cursor() as cur:
            cur.execute(
                _LABEL_SELECT + " WHERE public_identifier = ?",
                (public_identifier,),
            )
            row = cur.fetchone()
        return _row_to_label(row) if row else None

    def get_by_client_idempotency_key(
        self, client_id: str, idempotency_key: str
    ) -> AisleLocationLabel | None:
        cid = (client_id or "").strip()
        key = (idempotency_key or "").strip()
        if not cid or not key:
            return None
        with self._client.cursor() as cur:
            cur.execute(
                _LABEL_SELECT + " WHERE client_id = ? AND idempotency_key = ?",
                (cid, key),
            )
            row = cur.fetchone()
        return _row_to_label(row) if row else None

    def list_by_location(
        self,
        location_id: str,
        *,
        status: str | None = None,
    ) -> Sequence[AisleLocationLabel]:
        with self._client.cursor() as cur:
            if status:
                cur.execute(
                    _LABEL_SELECT
                    + " WHERE location_id = ? AND status = ?"
                    + " ORDER BY generated_at DESC",
                    (location_id, status.upper()),
                )
            else:
                cur.execute(
                    _LABEL_SELECT
                    + " WHERE location_id = ? ORDER BY generated_at DESC",
                    (location_id,),
                )
            rows = cur.fetchall()
        return [_row_to_label(r) for r in rows]
