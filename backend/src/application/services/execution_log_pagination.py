"""Server-side pagination helpers for execution-log JSONL event arrays."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionLogPage:
    items: list[dict[str, Any]]
    next_cursor: str | None
    has_more: bool
    available_levels: list[str]
    available_stages: list[str]


def encode_log_cursor(offset: int) -> str:
    raw = f"e:{offset}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_log_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + pad).decode("utf-8")
        if raw.startswith("e:"):
            return max(0, int(raw[2:]))
    except Exception:
        return 0
    return 0


def paginate_execution_log_events(
    events: list[dict[str, Any]],
    *,
    cursor: str | None = None,
    limit: int = 100,
    max_limit: int = 500,
    level: str | None = None,
    stage: str | None = None,
    search: str | None = None,
    sort_order: str = "asc",
) -> ExecutionLogPage:
    """Filter + paginate an already-loaded event list.

    For small/medium logs this is correct and preserves existing storage.
    Callers must still avoid loading multi-GB files; readers should apply
    byte-size guards before invoking this helper.
    """
    levels: set[str] = set()
    stages: set[str] = set()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        lv = ev.get("level")
        st = ev.get("stage")
        if isinstance(lv, str) and lv.strip():
            levels.add(lv.strip())
        if isinstance(st, str) and st.strip():
            stages.add(st.strip())

    filtered: list[dict[str, Any]] = []
    level_f = (level or "").strip().lower() or None
    stage_f = (stage or "").strip() or None
    search_f = (search or "").strip().lower() or None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if level_f and str(ev.get("level") or "").strip().lower() != level_f:
            continue
        if stage_f and str(ev.get("stage") or "").strip() != stage_f:
            continue
        if search_f:
            msg = str(ev.get("message") or "").lower()
            blob = json.dumps(ev.get("payload") or {}, default=str).lower()
            if search_f not in msg and search_f not in blob:
                continue
        filtered.append(ev)

    reverse = (sort_order or "asc").strip().lower() == "desc"
    # Stable sort: timestamp then original index.
    indexed = list(enumerate(filtered))
    indexed.sort(
        key=lambda pair: (
            str((pair[1] or {}).get("ts") or ""),
            pair[0],
        ),
        reverse=reverse,
    )
    ordered = [ev for _, ev in indexed]

    limit_n = max(1, min(int(limit), int(max_limit)))
    offset = decode_log_cursor(cursor)
    window = ordered[offset : offset + limit_n]
    next_off = offset + len(window)
    has_more = next_off < len(ordered)
    return ExecutionLogPage(
        items=window,
        next_cursor=encode_log_cursor(next_off) if has_more else None,
        has_more=has_more,
        available_levels=sorted(levels),
        available_stages=sorted(stages),
    )
