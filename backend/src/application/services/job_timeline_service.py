"""Derive a structured Observability timeline from execution-log events (no new table required)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from src.application.services.execution_log_pagination import (
    decode_log_cursor,
    encode_log_cursor,
)


@dataclass(frozen=True)
class TimelineEventView:
    id: str
    job_id: str
    execution_id: str | None
    event_type: str
    stage: str | None
    level: str
    timestamp: str | None
    sequence: int
    previous_status: str | None
    new_status: str | None
    message: str | None
    duration_ms: int | None
    provider: str | None
    provider_request_id: str | None
    error_code: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TimelinePage:
    items: list[TimelineEventView]
    next_cursor: str | None
    has_more: bool


_STAGE_EVENT_MAP: dict[str, str] = {
    "queued": "JOB_QUEUED",
    "dequeue": "JOB_DEQUEUED",
    "worker": "WORKER_STARTED",
    "input": "SOURCE_ASSETS_RESOLVED",
    "preprocess": "PREPROCESSING_STARTED",
    "preprocessing": "PREPROCESSING_STARTED",
    "provider": "PROVIDER_REQUEST_STARTED",
    "llm": "PROVIDER_REQUEST_STARTED",
    "parse": "RESPONSE_PARSING_STARTED",
    "parsing": "RESPONSE_PARSING_STARTED",
    "persist": "RESULT_PERSIST_STARTED",
    "persistence": "RESULT_PERSIST_STARTED",
    "artifact": "ARTIFACT_PUBLICATION_STARTED",
    "finalization": "ARTIFACT_PUBLICATION_STARTED",
    "cancel": "JOB_CANCEL_REQUESTED",
}


def _infer_event_type(ev: dict[str, Any]) -> str:
    explicit = ev.get("event_type") or ev.get("type")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().upper()
    stage = str(ev.get("stage") or "").strip().lower()
    level = str(ev.get("level") or "").strip().lower()
    msg = str(ev.get("message") or "").strip().lower()
    if level in {"error", "critical"} or "fail" in msg:
        if "provider" in stage or "llm" in stage:
            return "PROVIDER_REQUEST_FAILED"
        return "JOB_FAILED"
    if "succeed" in msg or "completed" in msg:
        if "provider" in stage:
            return "PROVIDER_REQUEST_COMPLETED"
        return "JOB_SUCCEEDED"
    if "retry" in msg:
        return "JOB_RETRY_CREATED"
    if "cancel" in msg or stage == "cancel":
        return "JOB_CANCELLED" if "cancel" in msg and "request" not in msg else "JOB_CANCEL_REQUESTED"
    if stage in _STAGE_EVENT_MAP:
        return _STAGE_EVENT_MAP[stage]
    return "PIPELINE_EVENT"


def _event_id(job_id: str, sequence: int, ev: dict[str, Any]) -> str:
    raw = f"{job_id}|{sequence}|{ev.get('ts')}|{ev.get('stage')}|{ev.get('message')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def derive_timeline_events(
    *,
    job_id: str,
    execution_id: str | None,
    raw_events: list[dict[str, Any]],
) -> list[TimelineEventView]:
    out: list[TimelineEventView] = []
    for idx, ev in enumerate(raw_events):
        if not isinstance(ev, dict):
            continue
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        provider = None
        req_id = None
        err_code = None
        duration = None
        if isinstance(payload, dict):
            provider = payload.get("provider") or payload.get("provider_name")
            req_id = payload.get("provider_request_id") or payload.get("request_id")
            err_code = payload.get("error_code") or payload.get("failure_code")
            dur = payload.get("duration_ms")
            if isinstance(dur, (int, float)):
                duration = int(dur)
        out.append(
            TimelineEventView(
                id=_event_id(job_id, idx, ev),
                job_id=str(ev.get("event_job_id") or job_id),
                execution_id=(
                    str(ev.get("event_execution_id"))
                    if ev.get("event_execution_id")
                    else execution_id
                ),
                event_type=_infer_event_type(ev),
                stage=str(ev.get("stage")) if ev.get("stage") is not None else None,
                level=str(ev.get("level") or "info"),
                timestamp=str(ev.get("ts")) if ev.get("ts") is not None else None,
                sequence=idx,
                previous_status=None,
                new_status=None,
                message=str(ev.get("message")) if ev.get("message") is not None else None,
                duration_ms=duration,
                provider=str(provider) if provider else None,
                provider_request_id=str(req_id) if req_id else None,
                error_code=str(err_code) if err_code else None,
                metadata={
                    k: v
                    for k, v in (payload or {}).items()
                    if k
                    not in {
                        "prompt_text",
                        "authorization",
                        "headers",
                        "api_key",
                    }
                },
            )
        )
    return out


def paginate_timeline(
    events: list[TimelineEventView],
    *,
    cursor: str | None = None,
    limit: int = 100,
    max_limit: int = 500,
    stage: str | None = None,
    event_type: str | None = None,
    level: str | None = None,
) -> TimelinePage:
    filtered = events
    if stage:
        s = stage.strip()
        filtered = [e for e in filtered if (e.stage or "") == s]
    if event_type:
        et = event_type.strip().upper()
        filtered = [e for e in filtered if e.event_type == et]
    if level:
        lv = level.strip().lower()
        filtered = [e for e in filtered if (e.level or "").lower() == lv]

    limit_n = max(1, min(int(limit), int(max_limit)))
    offset = decode_log_cursor(cursor)
    window = filtered[offset : offset + limit_n]
    next_off = offset + len(window)
    has_more = next_off < len(filtered)
    return TimelinePage(
        items=window,
        next_cursor=encode_log_cursor(next_off) if has_more else None,
        has_more=has_more,
    )
