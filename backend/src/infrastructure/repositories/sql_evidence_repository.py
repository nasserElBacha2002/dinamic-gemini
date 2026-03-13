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

logger = logging.getLogger(__name__)


def _parse_json(raw: Optional[str], context: str = "") -> Optional[Dict[str, Any]]:
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s", context or "evidence", e)
        return None


def _type_from_row(row, evidence_id: str = "?") -> EvidenceType:
    t = getattr(row, "type", "position_crop") or "position_crop"
    try:
        return EvidenceType(t)
    except ValueError:
        return EvidenceType.POSITION_CROP


def _row_to_evidence(row) -> Evidence:
    eid = getattr(row, "id", "")
    source_asset_id = getattr(row, "source_asset_id", None)
    if source_asset_id == "":
        source_asset_id = None
    return Evidence(
        id=eid,
        entity_type=row.entity_type or "",
        entity_id=row.entity_id or "",
        type=_type_from_row(row, eid),
        storage_path=row.storage_path or "",
        source_asset_id=source_asset_id,
        is_primary=bool(getattr(row, "is_primary", False)),
        frame_index=getattr(row, "frame_index", None),
        timestamp_ms=getattr(row, "timestamp_ms", None),
        bbox_json=_parse_json(getattr(row, "bbox_json", None), f"evidence id={eid}"),
        quality_score=getattr(row, "quality_score", None),
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
                    INSERT INTO evidences (id, entity_type, entity_id, type, storage_path, source_asset_id, is_primary, frame_index, timestamp_ms, bbox_json, quality_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence.id,
                        evidence.entity_type,
                        evidence.entity_id,
                        evidence.type.value,
                        evidence.storage_path,
                        source_asset_id,
                        evidence.is_primary,
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
                       frame_index, timestamp_ms, bbox_json, quality_score
                FROM evidences WHERE entity_type = ? AND entity_id = ?
                ORDER BY is_primary DESC, id ASC
                """,
                (entity_type, entity_id),
            )
            rows = cur.fetchall()
        return [_row_to_evidence(row) for row in rows]
