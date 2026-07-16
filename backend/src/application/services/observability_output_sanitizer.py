"""Central Observability output sanitization boundary."""

from __future__ import annotations

from typing import Any

from src.config import load_settings
from src.auth.schemas import AuthUser
from src.application.services.observability_access import (
    CAP_VIEW_FULL_PROMPT,
    CAP_VIEW_STACK_TRACES,
    principal_has_capability,
)
from src.pipeline.secret_redaction import redact_secrets_in_text, redact_secrets_in_value


_PROMPT_KEYS = frozenset(
    {
        "prompt_text",
        "full_prompt",
        "effective_prompt_text",
        "composed_prompt",
    }
)
_STACK_KEYS = frozenset(
    {
        "stack_trace",
        "traceback",
        "stack",
        "exc_info",
    }
)


def sanitize_observability_value(
    value: Any,
    *,
    user: AuthUser | None = None,
    allow_full_prompt: bool | None = None,
    allow_stack_traces: bool | None = None,
) -> Any:
    """Redact secrets and gate prompt/stack fields by capability + config."""
    settings = load_settings()
    cfg_prompt = bool(getattr(settings, "execution_log_include_full_prompt", False))
    if allow_full_prompt is None:
        allow_full_prompt = bool(
            user is not None
            and principal_has_capability(user, CAP_VIEW_FULL_PROMPT)
            and cfg_prompt
        )
    if allow_stack_traces is None:
        allow_stack_traces = bool(
            user is not None and principal_has_capability(user, CAP_VIEW_STACK_TRACES)
        )
    return _sanitize(
        value,
        allow_full_prompt=allow_full_prompt,
        allow_stack_traces=allow_stack_traces,
        depth=0,
    )


def sanitize_execution_log_events(
    events: list[dict[str, Any]],
    *,
    user: AuthUser | None,
) -> list[dict[str, Any]]:
    return [
        sanitize_observability_value(ev, user=user) if isinstance(ev, dict) else ev
        for ev in events
    ]


def _sanitize(
    value: Any,
    *,
    allow_full_prompt: bool,
    allow_stack_traces: bool,
    depth: int,
) -> Any:
    if depth > 24:
        return "[REDACTED_MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_secrets_in_text(value)
    if isinstance(value, list):
        return [
            _sanitize(
                v,
                allow_full_prompt=allow_full_prompt,
                allow_stack_traces=allow_stack_traces,
                depth=depth + 1,
            )
            for v in value
        ]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            key_l = key.lower()
            if key_l in _PROMPT_KEYS or key_l.endswith("prompt_text"):
                if allow_full_prompt:
                    out[key] = redact_secrets_in_text(str(v)) if v is not None else v
                else:
                    out[key] = "[REDACTED_BY_ROLE_OR_CONFIG]"
                continue
            if key_l in _STACK_KEYS:
                if allow_stack_traces:
                    out[key] = redact_secrets_in_text(str(v)) if v is not None else v
                else:
                    out[key] = "[REDACTED_STACK]"
                continue
            out[key] = _sanitize(
                v,
                allow_full_prompt=allow_full_prompt,
                allow_stack_traces=allow_stack_traces,
                depth=depth + 1,
            )
        return redact_secrets_in_value(out)
    return redact_secrets_in_text(str(value))
