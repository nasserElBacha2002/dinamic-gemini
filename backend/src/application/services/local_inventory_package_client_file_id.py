"""Normalize package photo ids to fit ``source_assets.upload_client_file_id``.

Column is ``VARCHAR(36)`` (multipart UUID-era idempotency). Mobile ZIP packages
often send ``{capture_session_id}:{media_store_id}`` which exceeds 36 chars and
caused SQL Server truncation 500s on confirm.
"""

from __future__ import annotations

import uuid

# Matches dbo.source_assets.upload_client_file_id (migration 0044).
SOURCE_ASSET_UPLOAD_CLIENT_FILE_ID_MAX = 36

_PKG_UPLOAD_CF_NS = uuid.UUID("b3c8e2f1-4a5d-4e6b-9c0d-1f2a3b4c5d6e")


def fit_source_asset_upload_client_file_id(
    raw: str | None,
    *,
    stable_key: str,
) -> str:
    """Return a value safe for ``upload_client_file_id`` (≤36), deterministic when shortened."""
    value = (raw or "").strip() or (stable_key or "").strip()
    if not value:
        return str(uuid.uuid4())
    if len(value) <= SOURCE_ASSET_UPLOAD_CLIENT_FILE_ID_MAX:
        return value
    return str(uuid.uuid5(_PKG_UPLOAD_CF_NS, f"local-pkg-cf:{value}"))
