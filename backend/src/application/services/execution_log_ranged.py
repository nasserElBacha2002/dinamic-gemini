"""Ranged JSONL execution-log access for Observability (no full-object download per page)."""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from typing import Any

from src.application.services.execution_log_incremental import (
    IncrementalLogPage,
    InvalidCursorError,
    encode_incremental_cursor,
    paginate_jsonl_stream,
)

logger = logging.getLogger(__name__)


class LogChangedError(ValueError):
    """Raised when the remote log object identity changed between pages."""


@dataclass(frozen=True)
class LogObjectIdentity:
    storage_key: str
    etag: str | None
    size_bytes: int


def identity_fingerprint(identity: LogObjectIdentity) -> str:
    raw = f"{identity.storage_key}|{identity.etag or ''}|{identity.size_bytes}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def encode_ranged_cursor(
    *,
    byte_offset: int,
    sequence: int,
    filters_fp: str,
    object_fp: str,
) -> str:
    # Reuse incremental encoder payload shape with object fingerprint in filters slot composition.
    # object_fp is folded into filters_fp by callers (filters_fp already versioned).
    return encode_incremental_cursor(
        byte_offset=byte_offset,
        sequence=sequence,
        filters_fp=f"{filters_fp}:{object_fp}",
    )


def filters_fp_with_object(*, filters_fp: str, object_fp: str) -> str:
    return f"{filters_fp}:{object_fp}"


def resolve_execution_log_meta(job: Any) -> tuple[str, str | None, dict[str, Any]] | None:
    """Return (storage_key, bucket_or_none, meta) when durable remote log metadata is complete."""
    from src.infrastructure.artifacts.stored_artifact_reader import provider_meta_complete
    from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
        DURABLE_ARTIFACT_KIND_EXECUTION_LOG,
    )

    rj = getattr(job, "result_json", None) or {}
    durable = rj.get("durable_artifacts") or {}
    meta = durable.get(DURABLE_ARTIFACT_KIND_EXECUTION_LOG)
    if not isinstance(meta, dict) or not provider_meta_complete(meta):
        return None
    key = (meta.get("storage_key") or "").strip()
    if not key:
        return None
    prov = (meta.get("storage_provider") or "").strip().lower()
    bucket = (meta.get("storage_bucket") or "").strip() or None
    dl_bucket = bucket if prov == "s3" else None
    return key, dl_bucket, meta


def paginate_execution_log_ranged(
    *,
    artifact_store: Any,
    storage_key: str,
    bucket: str | None,
    cursor: str | None,
    limit: int,
    max_limit: int,
    max_scan_bytes: int,
    level: str | None = None,
    stage: str | None = None,
    search: str | None = None,
    sort_order: str = "asc",
    expected_identity: LogObjectIdentity | None = None,
) -> tuple[IncrementalLogPage, LogObjectIdentity]:
    """Page a remote JSONL log using ranged reads (+ optional LOG_CHANGED detection)."""
    meta = artifact_store.get_object_metadata(storage_key, bucket=bucket)
    identity = LogObjectIdentity(
        storage_key=storage_key,
        etag=getattr(meta, "etag", None),
        size_bytes=int(getattr(meta, "file_size_bytes", 0) or 0),
    )
    if expected_identity is not None and (
        expected_identity.storage_key != identity.storage_key
        or (expected_identity.etag and identity.etag and expected_identity.etag != identity.etag)
        or (
            expected_identity.size_bytes
            and identity.size_bytes
            and expected_identity.size_bytes != identity.size_bytes
        )
    ):
        raise LogChangedError("LOG_CHANGED")

    obj_fp = identity_fingerprint(identity)
    from src.application.services.execution_log_incremental import _filters_fingerprint

    base_fp = _filters_fingerprint(
        level=level, stage=stage, search=search, sort_order=sort_order or "asc"
    )
    combined_fp = filters_fp_with_object(filters_fp=base_fp, object_fp=obj_fp)

    # Decode cursor against combined fingerprint (raises InvalidCursorError on mismatch).
    from src.application.services.execution_log_incremental import decode_incremental_cursor

    byte_offset, _seq = decode_incremental_cursor(cursor, filters_fp=combined_fp)

    # Read a window starting at the cursor offset (not from byte 0).
    window = artifact_store.read_range(
        storage_key,
        start=byte_offset,
        length=int(max_scan_bytes) + 65536,
        bucket=bucket,
    )
    # If starting mid-line (should not happen for server-issued cursors), skip to next newline.
    if byte_offset > 0 and window and window[0:1] != b"\n":
        nl = window.find(b"\n")
        if nl >= 0:
            window = window[nl + 1 :]
            byte_offset = byte_offset + nl + 1

    stream = io.BytesIO(window)
    # Force cursor=None and patch offsets: paginate from relative 0 then shift.
    page = paginate_jsonl_stream(
        stream,
        cursor=None,
        limit=limit,
        max_limit=max_limit,
        max_scan_bytes=max_scan_bytes,
        level=level,
        stage=stage,
        search=search,
        sort_order=sort_order,
    )
    # Rewrite next_cursor to absolute offsets + object identity.
    next_cursor = None
    if page.has_more and page.next_cursor:
        # Decode relative cursor from page (filters_fp without object).
        try:
            rel_off, rel_seq = decode_incremental_cursor(page.next_cursor, filters_fp=base_fp)
        except InvalidCursorError:
            # page encoder used base_fp; if that fails, treat as end.
            rel_off, rel_seq = 0, 0
        abs_off = byte_offset + rel_off
        next_cursor = encode_incremental_cursor(
            byte_offset=abs_off,
            sequence=rel_seq,
            filters_fp=combined_fp,
        )
    elif page.has_more:
        abs_off = byte_offset + page.bytes_scanned
        next_cursor = encode_incremental_cursor(
            byte_offset=abs_off,
            sequence=0,
            filters_fp=combined_fp,
        )

    return (
        IncrementalLogPage(
            items=page.items,
            next_cursor=next_cursor,
            has_more=page.has_more,
            mode="incremental",
            truncated=page.truncated,
            bytes_scanned=page.bytes_scanned,
            available_levels=page.available_levels,
            available_stages=page.available_stages,
        ),
        identity,
    )
