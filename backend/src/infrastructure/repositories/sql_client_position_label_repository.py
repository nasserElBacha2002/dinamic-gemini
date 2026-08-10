"""SQL Server client-scoped positioning label repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pyodbc

from src.application.errors import IdempotencyKeyReusedError
from src.database.sqlserver import SqlServerClient
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelArtifact,
    ClientPositionLabelSignatureStatus,
    ClientPositionLabelStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str


def _is_idempotency_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    return "uq_client_position_labels_client_idempotency" in str(exc).lower()


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _parse_payload(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("canonical_payload must be an object")
    return parsed


def _row_to_label(row) -> ClientPositionLabel:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "ACTIVE"
    try:
        status = ClientPositionLabelStatus(status_raw)
    except ValueError:
        status = ClientPositionLabelStatus.ACTIVE
    sig_raw = normalize_db_str(getattr(row, "signature_status", None)) or "UNSIGNED"
    try:
        signature_status = ClientPositionLabelSignatureStatus(sig_raw)
    except ValueError:
        signature_status = ClientPositionLabelSignatureStatus.UNSIGNED
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise ValueError("client_position_labels row missing timestamps")
    return ClientPositionLabel(
        id=normalize_db_str(getattr(row, "id", None)),
        client_id=normalize_db_str(getattr(row, "client_id", None)),
        public_identifier=normalize_db_str(getattr(row, "public_identifier", None)),
        name=normalize_db_str(getattr(row, "name", None)),
        normalized_name=normalize_db_str(getattr(row, "normalized_name", None)),
        status=status,
        payload_version=int(getattr(row, "payload_version", 1) or 1),
        canonical_payload=_parse_payload(getattr(row, "canonical_payload", None)),
        created_at=created,
        updated_at=updated,
        description=optional_nonempty_db_str(getattr(row, "description", None)),
        payload_hash=optional_nonempty_db_str(getattr(row, "payload_hash", None)),
        signature=optional_nonempty_db_str(getattr(row, "signature", None)),
        signature_algorithm=optional_nonempty_db_str(getattr(row, "signature_algorithm", None)),
        signature_key_version=(
            int(getattr(row, "signature_key_version"))
            if getattr(row, "signature_key_version", None) is not None
            else None
        ),
        signature_status=signature_status,
        created_by=optional_nonempty_db_str(getattr(row, "created_by", None)),
        invalidated_at=_ensure_utc(getattr(row, "invalidated_at", None)),
        invalidation_reason=optional_nonempty_db_str(getattr(row, "invalidation_reason", None)),
        idempotency_key=optional_nonempty_db_str(getattr(row, "idempotency_key", None)),
        idempotency_request_hash=optional_nonempty_db_str(
            getattr(row, "idempotency_request_hash", None)
        ),
        pallet=optional_nonempty_db_str(getattr(row, "pallet", None)),
        side=optional_nonempty_db_str(getattr(row, "side", None)),
        level=(
            int(getattr(row, "level"))
            if getattr(row, "level", None) is not None
            else None
        ),
        marker_index=(
            int(getattr(row, "marker_index"))
            if getattr(row, "marker_index", None) is not None
            else None
        ),
        marker_total=(
            int(getattr(row, "marker_total"))
            if getattr(row, "marker_total", None) is not None
            else None
        ),
    )


def _row_to_artifact(row) -> ClientPositionLabelArtifact:
    created = _ensure_utc(getattr(row, "created_at", None))
    if created is None:
        raise ValueError("client_position_label_artifacts row missing created_at")
    return ClientPositionLabelArtifact(
        id=normalize_db_str(getattr(row, "id", None)),
        label_id=normalize_db_str(getattr(row, "label_id", None)),
        format=normalize_db_str(getattr(row, "format", None)).upper(),
        preset=normalize_db_str(getattr(row, "preset", None)),
        template_version=int(getattr(row, "template_version", 1) or 1),
        marker_version=int(getattr(row, "marker_version", 1) or 1),
        content_type=normalize_db_str(getattr(row, "content_type", None)),
        file_size_bytes=int(getattr(row, "file_size_bytes", 0) or 0),
        artifact_hash=normalize_db_str(getattr(row, "artifact_hash", None)),
        storage_key=normalize_db_str(getattr(row, "storage_key", None)),
        created_at=created,
    )


_LABEL_SELECT = """
SELECT id, client_id, public_identifier, name, normalized_name, description, status,
       payload_version, canonical_payload, payload_hash, signature, signature_algorithm,
       signature_key_version, signature_status, created_by, created_at, updated_at,
       invalidated_at, invalidation_reason, idempotency_key, idempotency_request_hash,
       pallet, side, level, marker_index, marker_total
FROM client_position_labels
"""


class SqlClientPositionLabelRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_by_id(self, label_id: str) -> ClientPositionLabel | None:
        with self._client.cursor() as cur:
            cur.execute(_LABEL_SELECT + " WHERE id = ?", (label_id,))
            row = cur.fetchone()
        return _row_to_label(row) if row else None

    def get_by_ids(self, label_ids: list[str]) -> dict[str, ClientPositionLabel]:
        ids = list(dict.fromkeys(label_id for label_id in label_ids if label_id))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._client.cursor() as cur:
            cur.execute(_LABEL_SELECT + f" WHERE id IN ({placeholders})", tuple(ids))
            rows = [_row_to_label(row) for row in cur.fetchall()]
        return {row.id: row for row in rows}

    def get_by_public_identifier(self, public_identifier: str) -> ClientPositionLabel | None:
        pub = (public_identifier or "").strip()
        if not pub:
            return None
        with self._client.cursor() as cur:
            cur.execute(_LABEL_SELECT + " WHERE public_identifier = ?", (pub,))
            row = cur.fetchone()
        return _row_to_label(row) if row else None

    def get_by_idempotency_key(
        self, client_id: str, idempotency_key: str
    ) -> ClientPositionLabel | None:
        key = (idempotency_key or "").strip()
        if not key:
            return None
        with self._client.cursor() as cur:
            cur.execute(
                _LABEL_SELECT + " WHERE client_id = ? AND idempotency_key = ?",
                (client_id, key),
            )
            row = cur.fetchone()
        return _row_to_label(row) if row else None

    def get_active_by_normalized_name(
        self, client_id: str, normalized_name: str
    ) -> ClientPositionLabel | None:
        name = (normalized_name or "").strip().upper()
        with self._client.cursor() as cur:
            cur.execute(
                _LABEL_SELECT
                + " WHERE client_id = ? AND normalized_name = ? AND status = 'ACTIVE'",
                (client_id, name),
            )
            row = cur.fetchone()
        return _row_to_label(row) if row else None

    def list_by_client(
        self,
        client_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ClientPositionLabel]:
        clauses = ["client_id = ?"]
        params: list[Any] = [client_id]
        if status:
            clauses.append("status = ?")
            params.append(status.upper())
        if search and search.strip():
            clauses.append(
                "(LOWER(name) LIKE ? OR LOWER(ISNULL(description, '')) LIKE ?"
                " OR LOWER(public_identifier) LIKE ?)"
            )
            like = f"%{search.strip().lower()}%"
            params.extend([like, like, like])
        where = " AND ".join(clauses)
        sql = (
            _LABEL_SELECT
            + f" WHERE {where} ORDER BY created_at DESC, id DESC"
            + " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        )
        params.extend([int(offset), int(limit)])
        with self._client.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [_row_to_label(row) for row in rows]

    def count_by_client(
        self,
        client_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
    ) -> int:
        clauses = ["client_id = ?"]
        params: list[Any] = [client_id]
        if status:
            clauses.append("status = ?")
            params.append(status.upper())
        if search and search.strip():
            clauses.append(
                "(LOWER(name) LIKE ? OR LOWER(ISNULL(description, '')) LIKE ?"
                " OR LOWER(public_identifier) LIKE ?)"
            )
            like = f"%{search.strip().lower()}%"
            params.extend([like, like, like])
        where = " AND ".join(clauses)
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(1) AS cnt FROM client_position_labels WHERE {where}",
                tuple(params),
            )
            row = cur.fetchone()
        return int(getattr(row, "cnt", 0) or 0)

    def save(self, label: ClientPositionLabel) -> ClientPositionLabel:
        payload_json = json.dumps(label.canonical_payload, ensure_ascii=False, sort_keys=True)
        existing = self.get_by_id(label.id)
        try:
            with self._client.cursor() as cur:
                if existing is None:
                    cur.execute(
                        """
                        INSERT INTO client_position_labels (
                            id, client_id, public_identifier, name, normalized_name, description,
                            status, payload_version, canonical_payload, payload_hash,
                            signature, signature_algorithm, signature_key_version, signature_status,
                            created_by, created_at, updated_at, invalidated_at, invalidation_reason,
                            idempotency_key, idempotency_request_hash,
                            pallet, side, level, marker_index, marker_total
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?, ?,
                            ?, ?,
                            ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            label.id,
                            label.client_id,
                            label.public_identifier,
                            label.name,
                            label.normalized_name,
                            label.description,
                            label.status.value,
                            int(label.payload_version),
                            payload_json,
                            label.payload_hash,
                            label.signature,
                            label.signature_algorithm,
                            label.signature_key_version,
                            label.signature_status.value,
                            label.created_by,
                            label.created_at,
                            label.updated_at,
                            label.invalidated_at,
                            label.invalidation_reason,
                            label.idempotency_key,
                            label.idempotency_request_hash,
                            label.pallet,
                            label.side,
                            label.level,
                            label.marker_index,
                            label.marker_total,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE client_position_labels
                        SET name = ?, normalized_name = ?, description = ?, status = ?,
                            payload_version = ?, canonical_payload = ?, payload_hash = ?,
                            signature = ?, signature_algorithm = ?, signature_key_version = ?,
                            signature_status = ?, updated_at = ?, invalidated_at = ?,
                            invalidation_reason = ?, idempotency_key = ?,
                            idempotency_request_hash = ?,
                            pallet = ?, side = ?, level = ?, marker_index = ?, marker_total = ?
                        WHERE id = ?
                        """,
                        (
                            label.name,
                            label.normalized_name,
                            label.description,
                            label.status.value,
                            int(label.payload_version),
                            payload_json,
                            label.payload_hash,
                            label.signature,
                            label.signature_algorithm,
                            label.signature_key_version,
                            label.signature_status.value,
                            label.updated_at,
                            label.invalidated_at,
                            label.invalidation_reason,
                            label.idempotency_key,
                            label.idempotency_request_hash,
                            label.pallet,
                            label.side,
                            label.level,
                            label.marker_index,
                            label.marker_total,
                            label.id,
                        ),
                    )
        except pyodbc.IntegrityError as exc:
            if _is_idempotency_unique_violation(exc):
                raise IdempotencyKeyReusedError(
                    "IDEMPOTENCY_KEY_REUSED: key already registered"
                ) from exc
            raise
        return label

    def get_artifact(
        self,
        label_id: str,
        *,
        format: str,
        preset: str,
        template_version: int,
        marker_version: int,
    ) -> ClientPositionLabelArtifact | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, label_id, format, preset, template_version, marker_version,
                       content_type, file_size_bytes, artifact_hash, storage_key, created_at
                FROM client_position_label_artifacts
                WHERE label_id = ? AND format = ? AND preset = ?
                  AND template_version = ? AND marker_version = ?
                """,
                (label_id, format.upper(), preset, int(template_version), int(marker_version)),
            )
            row = cur.fetchone()
        return _row_to_artifact(row) if row else None

    def save_artifact(self, artifact: ClientPositionLabelArtifact) -> ClientPositionLabelArtifact:
        existing = self.get_artifact(
            artifact.label_id,
            format=artifact.format,
            preset=artifact.preset,
            template_version=artifact.template_version,
            marker_version=artifact.marker_version,
        )
        with self._client.cursor() as cur:
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO client_position_label_artifacts (
                        id, label_id, format, preset, template_version, marker_version,
                        content_type, file_size_bytes, artifact_hash, storage_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.id,
                        artifact.label_id,
                        artifact.format.upper(),
                        artifact.preset,
                        int(artifact.template_version),
                        int(artifact.marker_version),
                        artifact.content_type,
                        int(artifact.file_size_bytes),
                        artifact.artifact_hash,
                        artifact.storage_key,
                        artifact.created_at,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE client_position_label_artifacts
                    SET content_type = ?, file_size_bytes = ?, artifact_hash = ?, storage_key = ?
                    WHERE id = ?
                    """,
                    (
                        artifact.content_type,
                        int(artifact.file_size_bytes),
                        artifact.artifact_hash,
                        artifact.storage_key,
                        existing.id,
                    ),
                )
                artifact = ClientPositionLabelArtifact(
                    id=existing.id,
                    label_id=artifact.label_id,
                    format=artifact.format,
                    preset=artifact.preset,
                    template_version=artifact.template_version,
                    marker_version=artifact.marker_version,
                    content_type=artifact.content_type,
                    file_size_bytes=artifact.file_size_bytes,
                    artifact_hash=artifact.artifact_hash,
                    storage_key=artifact.storage_key,
                    created_at=existing.created_at,
                )
        return artifact
