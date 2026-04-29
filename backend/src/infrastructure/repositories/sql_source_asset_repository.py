"""
SQL Server implementation of SourceAssetRepository — v3.0 Épica 4.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, cast

from src.application.ports.rollup_contracts import AisleAssetRollup
from src.application.ports.repositories import SourceAssetRepository
from src.database.sqlserver import SqlServerClient
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.storage.sql_storage_fields import resolved_storage_key_for_row

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _type_from_row(row, asset_id: str = "?") -> SourceAssetType:
    type_str = getattr(row, "type", "photo") or "photo"
    try:
        return SourceAssetType(type_str)
    except ValueError:
        logger.warning(
            "Invalid source_asset type from DB: %r, using PHOTO for asset_id=%s",
            type_str,
            asset_id,
        )
        return SourceAssetType.PHOTO


def _parse_metadata(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw or not raw.strip():
        return None
    try:
        return cast(Dict[str, Any], json.loads(raw))
    except json.JSONDecodeError as e:
        logger.warning("Invalid metadata_json in source_assets: %s", e)
        return None


def _row_to_asset(row) -> SourceAsset:
    aid = getattr(row, "id", "")
    uploaded = _ensure_utc(getattr(row, "uploaded_at", None))
    if uploaded is None:
        raise ValueError("source_assets row missing required uploaded_at")
    storage_path = (getattr(row, "storage_path", None) or "").strip()
    storage_provider_raw = (getattr(row, "storage_provider", None) or "").strip() or None
    storage_key = resolved_storage_key_for_row(
        storage_provider=storage_provider_raw,
        storage_key_raw=getattr(row, "storage_key", None),
        storage_path=storage_path,
    )
    # mime_type: domain/API; content_type: storage metadata (falls back to mime for legacy rows).
    content_type = (getattr(row, "content_type", None) or "").strip() or (getattr(row, "mime_type", None) or "")
    cap_item = (getattr(row, "capture_session_item_id", None) or "").strip() or None
    return SourceAsset(
        id=aid,
        aisle_id=row.aisle_id or "",
        type=_type_from_row(row, aid),
        original_filename=row.original_filename or "",
        storage_path=storage_path,
        mime_type=row.mime_type or "application/octet-stream",
        uploaded_at=uploaded,
        metadata_json=_parse_metadata(getattr(row, "metadata_json", None)),
        storage_provider=storage_provider_raw,
        storage_bucket=(getattr(row, "storage_bucket", None) or "").strip() or None,
        storage_key=storage_key or None,
        content_type=content_type or None,
        file_size_bytes=getattr(row, "file_size_bytes", None),
        etag=(getattr(row, "etag", None) or "").strip() or None,
        capture_session_item_id=cap_item,
    )


class SqlSourceAssetRepository(SourceAssetRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, asset: SourceAsset) -> None:
        uploaded = _ensure_utc(asset.uploaded_at)
        if uploaded is None:
            raise ValueError("SourceAsset.uploaded_at is required")
        meta_str = json.dumps(asset.metadata_json, ensure_ascii=False) if asset.metadata_json else None
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE source_assets
                SET aisle_id = ?, type = ?, original_filename = ?, storage_path = ?,
                    storage_provider = ?, storage_bucket = ?, storage_key = ?,
                    content_type = ?, file_size_bytes = ?, etag = ?,
                    mime_type = ?, uploaded_at = ?, metadata_json = ?,
                    capture_session_item_id = ?
                WHERE id = ?
                """,
                (
                    asset.aisle_id,
                    asset.type.value,
                    asset.original_filename,
                    asset.storage_path,
                    asset.storage_provider,
                    asset.storage_bucket,
                    asset.storage_key,
                    asset.content_type,
                    asset.file_size_bytes,
                    asset.etag,
                    asset.mime_type,
                    uploaded,
                    meta_str,
                    asset.capture_session_item_id,
                    asset.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO source_assets (
                        id, aisle_id, type, original_filename, storage_path,
                        storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                        mime_type, uploaded_at, metadata_json, capture_session_item_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset.id,
                        asset.aisle_id,
                        asset.type.value,
                        asset.original_filename,
                        asset.storage_path,
                        asset.storage_provider,
                        asset.storage_bucket,
                        asset.storage_key,
                        asset.content_type,
                        asset.file_size_bytes,
                        asset.etag,
                        asset.mime_type,
                        uploaded,
                        meta_str,
                        asset.capture_session_item_id,
                    ),
                )

    def get_by_id(self, asset_id: str) -> Optional[SourceAsset]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, aisle_id, type, original_filename, storage_path,
                       storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                       mime_type, uploaded_at, metadata_json, capture_session_item_id
                FROM source_assets WHERE id = ?
                """,
                (asset_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_asset(row)

    def delete_by_id(self, asset_id: str) -> bool:
        with self._client.cursor() as cur:
            cur.execute("DELETE FROM source_assets WHERE id = ?", (asset_id,))
            return cur.rowcount > 0

    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> Optional[SourceAsset]:
        cid = (capture_session_item_id or "").strip()
        if not cid:
            return None
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, aisle_id, type, original_filename, storage_path,
                       storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                       mime_type, uploaded_at, metadata_json, capture_session_item_id
                FROM source_assets WHERE capture_session_item_id = ?
                """,
                (cid,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_asset(row)

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, aisle_id, type, original_filename, storage_path,
                       storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                       mime_type, uploaded_at, metadata_json, capture_session_item_id
                FROM source_assets WHERE aisle_id = ? ORDER BY uploaded_at ASC
                """,
                (aisle_id,),
            )
            rows = cur.fetchall()
        return [_row_to_asset(row) for row in rows]

    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> Dict[str, AisleAssetRollup]:
        if not aisle_ids:
            return {}
        placeholders = ",".join("?" * len(aisle_ids))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT aisle_id, COUNT(*) AS cnt, MAX(uploaded_at) AS max_uploaded
                FROM source_assets
                WHERE aisle_id IN ({placeholders})
                GROUP BY aisle_id
                """,
                list(aisle_ids),
            )
            rows = cur.fetchall()
        out: Dict[str, AisleAssetRollup] = {}
        for row in rows:
            aid = row.aisle_id or ""
            if not aid:
                continue
            cnt = int(getattr(row, "cnt", 0) or 0)
            raw_max = getattr(row, "max_uploaded", None)
            last = _ensure_utc(raw_max) if raw_max is not None else None
            out[aid] = AisleAssetRollup(count=cnt, last_uploaded_at=last)
        return out
