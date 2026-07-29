"""Phase 5 — structured logging helpers (incremental; does not rewrite all loggers)."""

from __future__ import annotations

import logging
from typing import Any

from src.observability.context import get_observability_context
from src.pipeline.secret_redaction import redact_secrets_in_text

logger = logging.getLogger("dinamic.observability")


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
    """Emit a queryable structured line; secrets are redacted."""
    ctx = get_observability_context().as_log_fields()
    parts: list[str] = [
        f"event={event}",
        f"component={component}",
    ]
    if operation:
        parts.append(f"operation={operation}")
    if outcome:
        parts.append(f"outcome={outcome}")
    if duration_ms is not None:
        parts.append(f"duration_ms={duration_ms:.3f}")
    if reason_code:
        parts.append(f"reason_code={reason_code}")
    for key, value in {**ctx, **fields}.items():
        if value is None:
            continue
        # IDs and codes only — never dump payloads.
        parts.append(f"{key}={value}")
    message = redact_secrets_in_text(" ".join(parts))
    logger.log(level, message)


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
