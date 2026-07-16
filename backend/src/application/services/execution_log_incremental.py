"""Incremental JSONL execution-log pagination without materializing the full file."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

logger = logging.getLogger(__name__)

CURSOR_VERSION = 1


class InvalidCursorError(ValueError):
    """Raised when a pagination cursor is malformed or filter-mismatched."""


@dataclass(frozen=True)
class IncrementalLogPage:
    items: list[dict[str, Any]]
    next_cursor: str | None
    has_more: bool
    mode: str  # "incremental" | "legacy_capped"
    truncated: bool
    bytes_scanned: int
    available_levels: list[str]
    available_stages: list[str]


def _filters_fingerprint(
    *,
    level: str | None,
    stage: str | None,
    search: str | None,
    sort_order: str,
) -> str:
    raw = json.dumps(
        {
            "level": (level or "").strip().lower(),
            "stage": (stage or "").strip(),
            "search": (search or "").strip().lower(),
            "sort": (sort_order or "asc").strip().lower(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def encode_incremental_cursor(
    *,
    byte_offset: int,
    sequence: int,
    filters_fp: str,
) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "o": int(byte_offset),
        "s": int(sequence),
        "f": filters_fp,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_incremental_cursor(cursor: str | None, *, filters_fp: str) -> tuple[int, int]:
    if not cursor:
        return 0, 0
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + pad)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise InvalidCursorError("INVALID_CURSOR") from exc
    if not isinstance(payload, dict) or payload.get("v") != CURSOR_VERSION:
        raise InvalidCursorError("INVALID_CURSOR")
    if payload.get("f") != filters_fp:
        raise InvalidCursorError("INVALID_CURSOR")
    try:
        return max(0, int(payload["o"])), max(0, int(payload["s"]))
    except Exception as exc:
        raise InvalidCursorError("INVALID_CURSOR") from exc


def _event_matches(
    ev: dict[str, Any],
    *,
    level: str | None,
    stage: str | None,
    search: str | None,
) -> bool:
    if level and str(ev.get("level") or "").strip().lower() != level:
        return False
    if stage and str(ev.get("stage") or "").strip() != stage:
        return False
    if search:
        msg = str(ev.get("message") or "").lower()
        blob = json.dumps(ev.get("payload") or {}, default=str).lower()
        if search not in msg and search not in blob:
            return False
    return True


def paginate_jsonl_stream(
    stream: BinaryIO,
    *,
    cursor: str | None,
    limit: int,
    max_limit: int,
    max_scan_bytes: int,
    level: str | None = None,
    stage: str | None = None,
    search: str | None = None,
    sort_order: str = "asc",
) -> IncrementalLogPage:
    """Read JSONL incrementally from ``stream`` using a byte-offset cursor.

    Only ``asc`` order is supported for true incremental reads. ``desc`` falls back
    to a capped full scan (``mode=legacy_capped``) with an explicit truncated flag.
    """
    limit_n = max(1, min(int(limit), int(max_limit)))
    level_f = (level or "").strip().lower() or None
    stage_f = (stage or "").strip() or None
    search_f = (search or "").strip().lower() or None
    sort = (sort_order or "asc").strip().lower()
    fp = _filters_fingerprint(
        level=level_f, stage=stage_f, search=search_f, sort_order=sort
    )

    if sort == "desc":
        return _legacy_capped_desc(
            stream,
            limit_n=limit_n,
            max_scan_bytes=max_scan_bytes,
            level=level_f,
            stage=stage_f,
            search=search_f,
            filters_fp=fp,
            cursor=cursor,
        )

    byte_offset, sequence = decode_incremental_cursor(cursor, filters_fp=fp)
    if byte_offset:
        stream.seek(byte_offset)

    items: list[dict[str, Any]] = []
    levels: set[str] = set()
    stages: set[str] = set()
    bytes_scanned = 0
    current_offset = byte_offset
    seq = sequence
    has_more = False
    truncated = False

    while True:
        line_start = stream.tell()
        line = stream.readline()
        if not line:
            break
        bytes_scanned += len(line)
        if bytes_scanned > max_scan_bytes:
            truncated = True
            has_more = True
            break
        current_offset = stream.tell()
        try:
            text = line.decode("utf-8").strip()
        except UnicodeDecodeError:
            text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            ev = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        lv = ev.get("level")
        st = ev.get("stage")
        if isinstance(lv, str) and lv.strip():
            levels.add(lv.strip())
        if isinstance(st, str) and st.strip():
            stages.add(st.strip())
        if not _event_matches(ev, level=level_f, stage=stage_f, search=search_f):
            continue
        # Stable identity under duplicate timestamps: attach sequence.
        ev = dict(ev)
        ev["_sequence"] = seq
        seq += 1
        if len(items) >= limit_n:
            has_more = True
            # Rewind so next cursor starts at this matching event's line.
            current_offset = line_start
            seq -= 1
            break
        items.append(ev)

    next_cursor = (
        encode_incremental_cursor(byte_offset=current_offset, sequence=seq, filters_fp=fp)
        if has_more
        else None
    )
    return IncrementalLogPage(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        mode="incremental",
        truncated=truncated,
        bytes_scanned=bytes_scanned,
        available_levels=sorted(levels),
        available_stages=sorted(stages),
    )


def _legacy_capped_desc(
    stream: BinaryIO,
    *,
    limit_n: int,
    max_scan_bytes: int,
    level: str | None,
    stage: str | None,
    search: str | None,
    filters_fp: str,
    cursor: str | None,
) -> IncrementalLogPage:
    """Capped reverse page — does not claim scalable pagination."""
    # Reject filter-mismatched cursors even in fallback.
    offset_idx, _ = decode_incremental_cursor(cursor, filters_fp=filters_fp)
    data = stream.read(max_scan_bytes + 1)
    truncated = len(data) > max_scan_bytes
    data = data[:max_scan_bytes]
    events: list[dict[str, Any]] = []
    for i, line in enumerate(data.splitlines()):
        try:
            text = line.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if not text:
            continue
        try:
            ev = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict) and _event_matches(
            ev, level=level, stage=stage, search=search
        ):
            ev = dict(ev)
            ev["_sequence"] = i
            events.append(ev)
    events.reverse()
    window = events[offset_idx : offset_idx + limit_n]
    next_off = offset_idx + len(window)
    has_more = next_off < len(events) or truncated
    next_cursor = (
        encode_incremental_cursor(byte_offset=next_off, sequence=next_off, filters_fp=filters_fp)
        if has_more
        else None
    )
    levels = sorted(
        {str(e.get("level")).strip() for e in events if isinstance(e.get("level"), str)}
    )
    stages = sorted(
        {str(e.get("stage")).strip() for e in events if isinstance(e.get("stage"), str)}
    )
    return IncrementalLogPage(
        items=window,
        next_cursor=next_cursor,
        has_more=has_more,
        mode="legacy_capped",
        truncated=truncated,
        bytes_scanned=len(data),
        available_levels=levels,
        available_stages=stages,
    )


def open_execution_log_tempfile(job: Any, *, artifact_store: Any) -> tuple[Path, bool]:
    """Download durable log to a temp file (or open legacy path). Returns (path, is_temp)."""
    from src.config import load_settings
    from src.infrastructure.artifacts.stored_artifact_reader import (
        StoredArtifactAccessError,
        ensure_remote_bucket_matches_configured,
        provider_meta_complete,
    )
    from src.infrastructure.pipeline.v3_job_executor import RUN_ID
    from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
        DURABLE_ARTIFACT_KIND_EXECUTION_LOG,
    )

    settings = load_settings()
    rj = getattr(job, "result_json", None) or {}
    durable = rj.get("durable_artifacts") or {}
    meta = durable.get(DURABLE_ARTIFACT_KIND_EXECUTION_LOG)
    if meta is not None and not provider_meta_complete(meta):
        raise StoredArtifactAccessError(
            404,
            "Execution log durable artifact metadata is incomplete.",
            "incomplete_metadata",
        )
    if meta and provider_meta_complete(meta):
        ensure_remote_bucket_matches_configured(meta, artifact_store)
        prov = (meta.get("storage_provider") or "").strip().lower()
        key = (meta.get("storage_key") or "").strip()
        bucket = (meta.get("storage_bucket") or "").strip() or None
        dl_bucket = bucket if prov == "s3" else None
        fd, tmp_name = tempfile.mkstemp(prefix="exec_log_page_", suffix=".jsonl")
        os.close(fd)
        tmp_path = Path(tmp_name)
        artifact_store.download_to_path(key, tmp_path, bucket=dl_bucket)
        return tmp_path, True

    if not settings.artifact_storage_legacy_local_read_enabled:
        raise StoredArtifactAccessError(
            404,
            "Execution log not available.",
            "legacy_local_disabled",
        )
    legacy = Path(settings.output_dir) / getattr(job, "id", "x") / RUN_ID / "execution_log.jsonl"
    if not legacy.is_file():
        raise StoredArtifactAccessError(404, "Execution log not found.", "missing")
    return legacy, False
