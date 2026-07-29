"""Phase 5 — structured logging helpers (JSON lines, secret-safe)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.observability.context import get_observability_context
from src.pipeline.secret_redaction import redact_secrets_in_text

logger = logging.getLogger("dinamic.observability")

_SAFE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_FORBIDDEN_FIELD_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "authorization",
        "api_key",
        "connection_string",
        "prompt",
        "payload",
    }
)


def _sanitize_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value)
    # Prevent log forging / multiline injection.
    text = text.replace("\r", " ").replace("\n", " ").replace("\x00", "")
    if len(text) > 256:
        text = text[:256]
    return redact_secrets_in_text(text)


def _sanitize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in fields.items():
        k = (key or "").strip()
        if not k or not _SAFE_KEY_RE.match(k):
            continue
        if k.lower() in _FORBIDDEN_FIELD_KEYS:
            continue
        out[k] = _sanitize_value(value)
    return out


def log_structured(
    level: int,
    *,
    event: str,
    component: str,
    operation: str | None = None,
    outcome: str | None = None,
    duration_ms: float | None = None,
    reason_code: str | None = None,
    **fields: Any,
) -> None:
    """Emit one JSON log object (single line)."""
    ctx = get_observability_context().as_log_fields()
    payload: dict[str, Any] = {
        "event": _sanitize_value(event),
        "component": _sanitize_value(component),
    }
    if operation is not None:
        payload["operation"] = _sanitize_value(operation)
    if outcome is not None:
        payload["outcome"] = _sanitize_value(outcome)
    if duration_ms is not None:
        payload["duration_ms"] = float(duration_ms)
    if reason_code is not None:
        payload["reason_code"] = _sanitize_value(reason_code)
    payload.update(_sanitize_fields({**ctx, **fields}))
    logger.log(level, json.dumps(payload, ensure_ascii=True, separators=(",", ":")))


def log_event(
    event: str,
    *,
    component: str,
    operation: str | None = None,
    outcome: str | None = None,
    duration_ms: float | None = None,
    reason_code: str | None = None,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    log_structured(
        level,
        event=event,
        component=component,
        operation=operation,
        outcome=outcome,
        duration_ms=duration_ms,
        reason_code=reason_code,
        **fields,
    )
