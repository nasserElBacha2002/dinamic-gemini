"""
SQL Server implementation of EvidenceRepository — v3.0 Épica 6.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Sequence

from src.application.ports.repositories import EvidenceRepository
from src.database.sqlserver import SqlServerClient
from src.domain.evidence.entities import Evidence, EvidenceType
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str
from src.infrastructure.storage.sql_storage_fields import resolved_storage_key_for_row

logger = logging.getLogger(__name__)


def _parse_json(raw: object, context: str = "") -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
    else:
        text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s", context or "evidence", e)
        return None
    if not isinstance(parsed, dict):
        logger.warning("JSON root is not an object in %s", context or "evidence")
        return None
    return parsed


def _type_from_row(row, evidence_id: str = "?") -> EvidenceType:
    raw = getattr(row, "type", None)
    t = normalize_db_str(raw) if raw is not None else ""
    if not t:
        t = "position_crop"
    try:
        return EvidenceType(t)
    except ValueError:
        return EvidenceType.POSITION_CROP


def _row_to_evidence(row) -> Evidence:
    eid = normalize_db_str(getattr(row, "id", None))
    source_asset_id = optional_nonempty_db_str(getattr(row, "source_asset_id", None))
    storage_path = normalize_db_str(getattr(row, "storage_path", None))
    storage_provider_raw = optional_nonempty_db_str(getattr(row, "storage_provider", None))
    storage_key = resolved_storage_key_for_row(
        storage_provider=storage_provider_raw,
        storage_key_raw=getattr(row, "storage_key", None),
        storage_path=storage_path,
    )
    # Evidence entity stores HTTP/storage metadata in content_type (no separate mime_type column).
    content_type = normalize_db_str(getattr(row, "content_type", None))
    return Evidence(
        id=eid,
        entity_type=normalize_db_str(getattr(row, "entity_type", None)),
        entity_id=normalize_db_str(getattr(row, "entity_id", None)),
        type=_type_from_row(row, eid),
        storage_path=storage_path,
        source_asset_id=source_asset_id,
        is_primary=bool(getattr(row, "is_primary", False)),
        frame_index=getattr(row, "frame_index", None),
        timestamp_ms=getattr(row, "timestamp_ms", None),
        bbox_json=_parse_json(getattr(row, "bbox_json", None), f"evidence id={eid}"),
        quality_score=getattr(row, "quality_score", None),
        storage_provider=storage_provider_raw,
        storage_bucket=optional_nonempty_db_str(getattr(row, "storage_bucket", None)),
        storage_key=storage_key or None,
        content_type=content_type or None,
        file_size_bytes=getattr(row, "file_size_bytes", None),
        etag=optional_nonempty_db_str(getattr(row, "etag", None)),
    )


class SqlEvidenceRepository(EvidenceRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, evidence: Evidence) -> None:
        bbox_str = json.dumps(evidence.bbox_json, ensure_ascii=False) if evidence.bbox_json else None
        source_asset_id = evidence.source_asset_id  # None stored as NULL
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE evidences
                SET entity_type = ?, entity_id = ?, type = ?, storage_path = ?, source_asset_id = ?, is_primary = ?,
                    storage_provider = ?, storage_bucket = ?, storage_key = ?, content_type = ?, file_size_bytes = ?, etag = ?,
                    frame_index = ?, timestamp_ms = ?, bbox_json = ?, quality_score = ?
                WHERE id = ?
                """,
                (
                    evidence.entity_type,
                    evidence.entity_id,
                    evidence.type.value,
                    evidence.storage_path,
                    source_asset_id,
                    evidence.is_primary,
                    evidence.storage_provider,
                    evidence.storage_bucket,
                    evidence.storage_key,
                    evidence.content_type,
                    evidence.file_size_bytes,
                    evidence.etag,
                    evidence.frame_index,
                    evidence.timestamp_ms,
                    bbox_str,
                    evidence.quality_score,
                    evidence.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO evidences (
                        id, entity_type, entity_id, type, storage_path, source_asset_id, is_primary,
                        storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                        frame_index, timestamp_ms, bbox_json, quality_score
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence.id,
                        evidence.entity_type,
                        evidence.entity_id,
                        evidence.type.value,
                        evidence.storage_path,
                        source_asset_id,
                        evidence.is_primary,
                        evidence.storage_provider,
                        evidence.storage_bucket,
                        evidence.storage_key,
                        evidence.content_type,
                        evidence.file_size_bytes,
                        evidence.etag,
                        evidence.frame_index,
                        evidence.timestamp_ms,
                        bbox_str,
                        evidence.quality_score,
                    ),
                )

    def get_by_id(self, evidence_id: str) -> Optional[Evidence]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, entity_type, entity_id, type, storage_path, source_asset_id, is_primary,
                       storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                       frame_index, timestamp_ms, bbox_json, quality_score
                FROM evidences WHERE id = ?
                """,
                (evidence_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_evidence(row)

    def list_by_entity(self, entity_type: str, entity_id: str) -> Sequence[Evidence]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, entity_type, entity_id, type, storage_path, source_asset_id, is_primary,
                       storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                       frame_index, timestamp_ms, bbox_json, quality_score
                FROM evidences WHERE entity_type = ? AND entity_id = ?
                ORDER BY is_primary DESC, id ASC
                """,
                (entity_type, entity_id),
            )
            rows = cur.fetchall()
        return [_row_to_evidence(row) for row in rows]
