"""Centralized secret / credential redaction for Observability surfaces."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|passwd|pwd|api[_-]?key|authorization|cookie|connection[_-]?string|"
    r"access[_-]?token|refresh[_-]?token|bearer|private[_-]?key)",
    re.IGNORECASE,
)

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"\bsk-(?:ant|proj|or-v1)-[A-Za-z0-9\-_]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(access_token|refresh_token|api_key|authorization)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(X-Amz-Security-Token|X-Amz-Credential)=[^&\s]+"),
    re.compile(r"https?://[^\s]*[?&](Signature|X-Amz-Signature)=[^\s]+"),
    re.compile(r"(?i)(Server=|UID=|PWD=|Password=)[^;]+"),
]


def redact_secrets_in_text(value: str | None) -> str:
    if not value:
        return ""
    out = value
    for pat in _PATTERNS:
        out = pat.sub(REDACTED, out)
    return out


def redact_secrets_in_value(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 24:
        return REDACTED
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_secrets_in_text(value)
    if isinstance(value, list):
        return [redact_secrets_in_value(v, _depth=_depth + 1) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if _SENSITIVE_KEY_RE.search(key):
                out[key] = REDACTED
            else:
                out[key] = redact_secrets_in_value(v, _depth=_depth + 1)
        return out
    return redact_secrets_in_text(str(value))
