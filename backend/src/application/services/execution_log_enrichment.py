"""
Enrich raw execution_log.jsonl events for API responses (filtering + plaintext export).

Reads normalized fields from each event's ``payload`` when present:
``job_id``, ``attempt``, ``execution_id`` or ``details.execution_id``.

Does not reorder or mutate raw event fields beyond building API view dicts.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


def _as_nonempty_str(value: Any) -> Optional[str]:
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
    except Exception:
        return None


def _as_attempt(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        iv = int(value)
        return iv if iv >= 0 else None
    if isinstance(value, str):
        t = value.strip()
        if not t:
            return None
        try:
            iv = int(t)
            return iv if iv >= 0 else None
        except ValueError:
            return None
    return None


def _execution_id_from_payload(payload: Any) -> Optional[str]:
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
) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """Return (job_id, attempt, execution_id) from a log event payload."""
    if not isinstance(payload, dict):
        return None, None, None
    job_id = _as_nonempty_str(payload.get("job_id"))
    attempt = _as_attempt(payload.get("attempt"))
    exec_id = _execution_id_from_payload(payload)
    return job_id, attempt, exec_id


def _is_requested_job_event(
    event_job_id: Optional[str],
    requested_job_id: str,
    any_event_has_job_id: bool,
) -> bool:
    if event_job_id is not None:
        return event_job_id == requested_job_id
    # Legacy / sparse: lines with no job_id — treat as this job only when no line
    # carried job context (single-artifact assumption).
    return not any_event_has_job_id


def build_enriched_execution_log(
    *,
    inventory_id: str,
    aisle_id: str,
    requested_job_id: str,
    raw_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build API-ready dict: metadata + events with derived fields. Preserves event order."""
    per_event_meta: List[Tuple[Optional[str], Optional[int], Optional[str]]] = []
    job_ids_seen: List[str] = []
    attempts_seen: List[int] = []
    exec_ids_seen: List[str] = []

    for ev in raw_events:
        payload = ev.get("payload")
        jid, att, eid = extract_event_context(payload)
        per_event_meta.append((jid, att, eid))
        if jid is not None:
            job_ids_seen.append(jid)
        if att is not None:
            attempts_seen.append(att)
        if eid is not None:
            exec_ids_seen.append(eid)

    any_event_has_job_id = any(j is not None for j, _, _ in per_event_meta)
    available_job_ids = sorted(set(job_ids_seen))
    if requested_job_id and requested_job_id not in available_job_ids:
        available_job_ids = [requested_job_id, *available_job_ids]
    if not available_job_ids and requested_job_id:
        available_job_ids = [requested_job_id]

    available_attempts = sorted(set(attempts_seen))
    available_execution_ids = sorted(set(exec_ids_seen))

    events_out: List[Dict[str, Any]] = []
    for ev, (jid, att, eid) in zip(raw_events, per_event_meta):
        ts = str(ev.get("ts", "") or "")
        stage = str(ev.get("stage", "") or "")
        level = str(ev.get("level", "") or "")
        message = str(ev.get("message", "") or "")
        payload = ev.get("payload")

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
                "is_requested_job_event": _is_requested_job_event(
                    jid, requested_job_id, any_event_has_job_id
                ),
            }
        )

    return {
        "inventory_id": inventory_id,
        "aisle_id": aisle_id,
        "requested_job_id": requested_job_id,
        "available_job_ids": available_job_ids,
        "available_attempts": available_attempts,
        "available_execution_ids": available_execution_ids,
        "events": events_out,
    }


def execution_log_attachment_filename(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> str:
    return f"inventory_{inventory_id}_aisle_{aisle_id}_job_{job_id}_execution_log.txt"


def format_execution_log_plaintext(enriched_events: List[Dict[str, Any]]) -> str:
    """
    Human-readable export: one header line, message line, optional payload line per entry;
    entries separated by a blank line.
    """
    blocks: List[str] = []
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
