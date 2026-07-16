"""Structured job errors for Observability (job row + execution-log error events)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from src.application.services.execution_log_pagination import (
    decode_log_cursor,
    encode_log_cursor,
)
from src.domain.jobs.entities import Job
from src.pipeline.secret_redaction import redact_secrets_in_text


@dataclass(frozen=True)
class JobErrorView:
    error_id: str
    job_id: str
    stage: str | None
    error_category: str | None
    error_code: str | None
    provider: str | None
    provider_code: str | None
    provider_request_id: str | None
    http_status: int | None
    message: str | None
    sanitized_detail: str | None
    retryable: bool | None
    attempt_number: int | None
    occurred_at: str | None
    stack_trace_available: bool


@dataclass(frozen=True)
class JobErrorPage:
    items: list[JobErrorView]
    next_cursor: str | None
    has_more: bool


def _id(*parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def collect_job_errors(
    job: Job,
    *,
    raw_events: list[dict[str, Any]],
    include_stack_hint: bool = False,
) -> list[JobErrorView]:
    items: list[JobErrorView] = []
    if job.failure_code or job.failure_message:
        detail = redact_secrets_in_text(job.failure_message or "")
        items.append(
            JobErrorView(
                error_id=_id(job.id, "primary", job.failure_code or ""),
                job_id=job.id,
                stage="job",
                error_category="job_failure",
                error_code=job.failure_code,
                provider=job.provider_name,
                provider_code=None,
                provider_request_id=None,
                http_status=None,
                message=detail or None,
                sanitized_detail=detail or None,
                retryable=None,
                attempt_number=job.attempt_count,
                occurred_at=job.finished_at.isoformat() if job.finished_at else None,
                stack_trace_available=False,
            )
        )

    for idx, ev in enumerate(raw_events):
        if not isinstance(ev, dict):
            continue
        level = str(ev.get("level") or "").lower()
        if level not in {"error", "critical"}:
            continue
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        msg = redact_secrets_in_text(str(ev.get("message") or ""))
        detail_raw = payload.get("detail") or payload.get("error") or payload.get("sanitized_detail")
        detail = redact_secrets_in_text(str(detail_raw)) if detail_raw is not None else msg
        stack_present = bool(payload.get("stack_trace") or payload.get("traceback"))
        items.append(
            JobErrorView(
                error_id=_id(job.id, "ev", idx, ev.get("ts")),
                job_id=job.id,
                stage=str(ev.get("stage")) if ev.get("stage") is not None else None,
                error_category="execution_log",
                error_code=(
                    str(payload.get("error_code") or payload.get("failure_code"))
                    if (payload.get("error_code") or payload.get("failure_code"))
                    else None
                ),
                provider=(
                    str(payload.get("provider") or payload.get("provider_name"))
                    if (payload.get("provider") or payload.get("provider_name"))
                    else job.provider_name
                ),
                provider_code=(
                    str(payload.get("provider_code")) if payload.get("provider_code") else None
                ),
                provider_request_id=(
                    str(payload.get("provider_request_id") or payload.get("request_id"))
                    if (payload.get("provider_request_id") or payload.get("request_id"))
                    else None
                ),
                http_status=(
                    int(payload["http_status"])
                    if isinstance(payload.get("http_status"), (int, float))
                    else None
                ),
                message=msg or None,
                sanitized_detail=detail or None,
                retryable=(
                    bool(payload["retryable"]) if isinstance(payload.get("retryable"), bool) else None
                ),
                attempt_number=job.attempt_count,
                occurred_at=str(ev.get("ts")) if ev.get("ts") is not None else None,
                stack_trace_available=bool(include_stack_hint and stack_present),
            )
        )
    return items


def paginate_job_errors(
    items: list[JobErrorView],
    *,
    cursor: str | None = None,
    limit: int = 100,
    max_limit: int = 500,
) -> JobErrorPage:
    limit_n = max(1, min(int(limit), int(max_limit)))
    offset = decode_log_cursor(cursor)
    window = items[offset : offset + limit_n]
    next_off = offset + len(window)
    has_more = next_off < len(items)
    return JobErrorPage(
        items=window,
        next_cursor=encode_log_cursor(next_off) if has_more else None,
        has_more=has_more,
    )
