"""
Enrich raw execution_log.jsonl events for API responses (filtering + plaintext export).

Reads normalized fields from each event's ``payload`` when present:
``job_id``, ``attempt``, ``execution_id`` or ``details.execution_id``.

Does not reorder or mutate raw event fields beyond building API view dicts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_execution_log_filename_segment(segment: str) -> str:
    """Make a single path segment safe for Content-Disposition filenames."""
    if not segment:
        return "unknown"
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", str(segment).strip())
    cleaned = cleaned.strip("._-") or "unknown"
    return cleaned[:200]


def _as_nonempty_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    try:
        s = str(value).strip()
        return s if s else None
    except (TypeError, ValueError, AttributeError):
        return None


def _non_negative_int_or_none(n: int) -> int | None:
    return n if n >= 0 else None


def _as_attempt(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    out: int | None = None
    if isinstance(value, int):
        out = _non_negative_int_or_none(value)
    elif isinstance(value, float) and value.is_integer():
        out = _non_negative_int_or_none(int(value))
    elif isinstance(value, str):
        t = value.strip()
        if t:
            try:
                out = _non_negative_int_or_none(int(t))
            except ValueError:
                out = None
    return out


def _execution_id_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    eid = _as_nonempty_str(payload.get("execution_id"))
    if eid:
        return eid
    details = payload.get("details")
    if isinstance(details, dict):
        return _as_nonempty_str(details.get("execution_id"))
    return None


def extract_event_context(
    payload: Any,
) -> tuple[str | None, int | None, str | None]:
    """Return (job_id, attempt, execution_id) from a log event payload."""
    if not isinstance(payload, dict):
        return None, None, None
    job_id = _as_nonempty_str(payload.get("job_id"))
    attempt = _as_attempt(payload.get("attempt"))
    exec_id = _execution_id_from_payload(payload)
    return job_id, attempt, exec_id


def _is_requested_job_event(
    event_job_id: str | None,
    requested_job_id: str,
    any_event_has_job_id: bool,
) -> bool:
    if event_job_id is not None:
        return event_job_id == requested_job_id
    # Legacy / sparse: lines with no job_id — treat as this job only when no line
    # carried job context (single-artifact assumption).
    return not any_event_has_job_id


def parse_ts_sort_key(ts_val: Any) -> tuple[int, float, str]:
    """Return (quality, epoch_seconds_or_0, raw) for global ordering. Lower sorts earlier.

    quality: 0 = parsed timestamp, 1 = missing/empty ts, 2 = unparseable string.
    """
    if ts_val is None:
        return (1, 0.0, "")
    s = str(ts_val).strip()
    if not s:
        return (1, 0.0, "")
    try:
        iso = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        return (0, dt.timestamp(), s)
    except ValueError:
        return (2, 0.0, s)


def merge_raw_execution_log_events_by_ts(
    job_streams: list[tuple[str, datetime, list[dict[str, Any]]]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Merge per-job streams into one list ordered by event timestamp (stable).

    ``job_streams`` items are ``(job_id, job_created_at, events in original file order)``.
    Tie-break when timestamps compare equal: older job first (smaller ``created_at``),
    then ``job_id``, then line index within the file.
    """
    entries: list[tuple[dict[str, Any], str, int, datetime]] = []
    for job_id, created_at, events in job_streams:
        for line_idx, ev in enumerate(events):
            entries.append((ev, job_id, line_idx, created_at))
    entries.sort(
        key=lambda t: (
            parse_ts_sort_key(t[0].get("ts")),
            t[3].timestamp(),
            t[1],
            t[2],
        )
    )
    if not entries:
        return [], []
    return [e[0] for e in entries], [e[1] for e in entries]


def _collect_execution_log_event_meta(
    raw_events: list[dict[str, Any]],
    artifact_owner_job_ids: list[str] | None,
) -> tuple[
    list[tuple[str | None, int | None, str | None]],
    list[str],
    list[int],
    list[str],
]:
    """First pass: per-event job/attempt/exec ids and dedupe lists for filter dropdowns."""
    per_event_meta: list[tuple[str | None, int | None, str | None]] = []
    job_ids_seen: list[str] = []
    attempts_seen: list[int] = []
    exec_ids_seen: list[str] = []

    for i, ev in enumerate(raw_events):
        payload = ev.get("payload")
        jid, att, eid = extract_event_context(payload)
        if jid is None and artifact_owner_job_ids is not None:
            jid = artifact_owner_job_ids[i]
        per_event_meta.append((jid, att, eid))
        if jid is not None:
            job_ids_seen.append(jid)
        if att is not None:
            attempts_seen.append(att)
        if eid is not None:
            exec_ids_seen.append(eid)

    return per_event_meta, job_ids_seen, attempts_seen, exec_ids_seen


@dataclass(frozen=True)
class _AvailableJobAttemptExecutionListsInputs:
    raw_events: list[dict[str, Any]]
    seed_job_ids: list[str] | None
    job_ids_seen: list[str]
    attempts_seen: list[int]
    exec_ids_seen: list[str]
    requested_job_id_for_legacy_flags: str | None


def _available_job_attempt_execution_lists(
    inp: _AvailableJobAttemptExecutionListsInputs,
) -> tuple[list[str], list[int], list[str], bool]:
    """Aggregates available ids for UI filters and whether any raw line had job context."""
    payload_only_job_ids = [extract_event_context(ev.get("payload"))[0] for ev in inp.raw_events]
    any_event_has_job_id = any(j is not None for j in payload_only_job_ids)

    acc_ids = set(j for j in inp.job_ids_seen if j is not None)
    if inp.seed_job_ids:
        acc_ids |= set(inp.seed_job_ids)
    available_job_ids = sorted(acc_ids)
    req = inp.requested_job_id_for_legacy_flags
    if req and req not in available_job_ids:
        available_job_ids = [req, *available_job_ids]
    if not available_job_ids and req:
        available_job_ids = [req]

    available_attempts = sorted(set(inp.attempts_seen))
    available_execution_ids = sorted(set(inp.exec_ids_seen))
    return (
        available_job_ids,
        available_attempts,
        available_execution_ids,
        any_event_has_job_id,
    )


def _build_enriched_event_rows(
    raw_events: list[dict[str, Any]],
    per_event_meta: list[tuple[str | None, int | None, str | None]],
    *,
    suppress_requested_job_flags: bool,
    requested_job_id_for_legacy_flags: str | None,
    any_event_has_job_id: bool,
) -> list[dict[str, Any]]:
    """Second pass: API-shaped rows with requested-job flags."""
    req = requested_job_id_for_legacy_flags
    events_out: list[dict[str, Any]] = []
    for ev, (jid, att, eid) in zip(raw_events, per_event_meta):
        ts = str(ev.get("ts", "") or "")
        stage = str(ev.get("stage", "") or "")
        level = str(ev.get("level", "") or "")
        message = str(ev.get("message", "") or "")
        payload = ev.get("payload")

        if suppress_requested_job_flags or not req:
            req_flag = False
        else:
            req_flag = _is_requested_job_event(jid, req, any_event_has_job_id)

        events_out.append(
            {
                "ts": ts,
                "stage": stage,
                "level": level,
                "message": message,
                "payload": payload,
                "event_job_id": jid,
                "event_attempt": att,
                "event_execution_id": eid,
                "is_requested_job_event": req_flag,
            }
        )
    return events_out


@dataclass(frozen=True)
class _EnrichedExecutionLogCoreParams:
    inventory_id: str
    aisle_id: str
    requested_job_id_out: str | None
    raw_events: list[dict[str, Any]]
    artifact_owner_job_ids: list[str] | None
    seed_job_ids: list[str] | None
    suppress_requested_job_flags: bool
    requested_job_id_for_legacy_flags: str | None


def _build_enriched_execution_log_core(params: _EnrichedExecutionLogCoreParams) -> dict[str, Any]:
    if params.artifact_owner_job_ids is not None and len(params.artifact_owner_job_ids) != len(
        params.raw_events
    ):
        raise ValueError("artifact_owner_job_ids length must match raw_events")

    per_event_meta, job_ids_seen, attempts_seen, exec_ids_seen = _collect_execution_log_event_meta(
        params.raw_events, params.artifact_owner_job_ids
    )
    (
        available_job_ids,
        available_attempts,
        available_execution_ids,
        any_event_has_job_id,
    ) = _available_job_attempt_execution_lists(
        _AvailableJobAttemptExecutionListsInputs(
            raw_events=params.raw_events,
            seed_job_ids=params.seed_job_ids,
            job_ids_seen=job_ids_seen,
            attempts_seen=attempts_seen,
            exec_ids_seen=exec_ids_seen,
            requested_job_id_for_legacy_flags=params.requested_job_id_for_legacy_flags,
        )
    )

    events_out = _build_enriched_event_rows(
        params.raw_events,
        per_event_meta,
        suppress_requested_job_flags=params.suppress_requested_job_flags,
        requested_job_id_for_legacy_flags=params.requested_job_id_for_legacy_flags,
        any_event_has_job_id=any_event_has_job_id,
    )

    return {
        "inventory_id": params.inventory_id,
        "aisle_id": params.aisle_id,
        "requested_job_id": params.requested_job_id_out,
        "available_job_ids": available_job_ids,
        "available_attempts": available_attempts,
        "available_execution_ids": available_execution_ids,
        "events": events_out,
    }


def build_enriched_execution_log(
    *,
    inventory_id: str,
    aisle_id: str,
    requested_job_id: str,
    raw_events: list[dict[str, Any]],
    artifact_owner_job_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build API-ready dict for a single-job execution log (existing contract)."""
    return _build_enriched_execution_log_core(
        _EnrichedExecutionLogCoreParams(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            requested_job_id_out=requested_job_id,
            raw_events=raw_events,
            artifact_owner_job_ids=artifact_owner_job_ids,
            seed_job_ids=None,
            suppress_requested_job_flags=False,
            requested_job_id_for_legacy_flags=requested_job_id,
        )
    )


# Public envelope: keep explicit kwargs for multi-job aggregated logs (callers / API contract).
def build_enriched_aisle_aggregated_execution_log(  # noqa: PLR0913
    *,
    inventory_id: str,
    aisle_id: str,
    raw_events: list[dict[str, Any]],
    artifact_owner_job_ids: list[str],
    seed_job_ids: list[str],
    jobs: list[dict[str, Any]],
    log_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Envelope for aisle-level aggregated logs (multi-job). ``requested_job_id`` is null."""
    core = _build_enriched_execution_log_core(
        _EnrichedExecutionLogCoreParams(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            requested_job_id_out=None,
            raw_events=raw_events,
            artifact_owner_job_ids=artifact_owner_job_ids,
            seed_job_ids=seed_job_ids,
            suppress_requested_job_flags=True,
            requested_job_id_for_legacy_flags=None,
        )
    )
    core["jobs"] = jobs
    core["log_sources"] = log_sources
    return core


def execution_log_attachment_filename(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> str:
    inv = sanitize_execution_log_filename_segment(inventory_id)
    aisle = sanitize_execution_log_filename_segment(aisle_id)
    job = sanitize_execution_log_filename_segment(job_id)
    return f"inventory_{inv}_aisle_{aisle}_job_{job}_execution_log.txt"


def aisle_execution_log_attachment_filename(inventory_id: str, aisle_id: str) -> str:
    inv = sanitize_execution_log_filename_segment(inventory_id)
    aisle = sanitize_execution_log_filename_segment(aisle_id)
    return f"inventory_{inv}_aisle_{aisle}_execution_log.txt"


def format_execution_log_plaintext(enriched_events: list[dict[str, Any]]) -> str:
    """
    Human-readable export: one header line, message line, optional payload line per entry;
    entries separated by a blank line.
    """
    blocks: list[str] = []
    for ev in enriched_events:
        ts = ev.get("ts") or ""
        stage = ev.get("stage") or ""
        level = ev.get("level") or ""
        message = ev.get("message") or ""
        jid = ev.get("event_job_id")
        att = ev.get("event_attempt")
        eid = ev.get("event_execution_id")

        parts = [f"[{ts}]", f"stage={stage}", f"level={level}"]
        if jid is not None:
            parts.append(f"job_id={jid}")
        if att is not None:
            parts.append(f"attempt={att}")
        if eid is not None:
            parts.append(f"execution_id={eid}")
        line1 = " ".join(parts)
        lines = [line1, f"message={message}"]
        payload = ev.get("payload")
        if payload is not None:
            try:
                lines.append(f"payload={json.dumps(payload, ensure_ascii=False)}")
            except (TypeError, ValueError):
                lines.append(f"payload={payload!r}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")
