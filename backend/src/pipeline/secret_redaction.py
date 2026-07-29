"""Centralized secret / credential redaction for Observability surfaces."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_RE = re.compile(
    r"(secret|password|passwd|pwd|api[_-]?key|authorization|cookie|connection[_-]?string|"
    r"access[_-]?token|refresh[_-]?token|bearer|private[_-]?key|"
    # Bare ``token`` but not usage metrics like ``input_tokens`` / ``output_tokens``.
    r"(?<![a-z0-9])token(?!s))",
    re.IGNORECASE,
)

# OCR / usage counters that contain ``token`` but are never secrets.
_SAFE_TOKEN_METRIC_KEY_RE = re.compile(
    r"(^|_)(normalized_)?token_count$|(^|_)tokens$|numeric_token_count|raw_numeric_token_count",
    re.IGNORECASE,
)

# Preserve URL/query structure: replace value only.
_SAS_QUERY_RE = re.compile(
    r"(?i)([?&])(sig|se|sv|sp|spr|srt|ss|st|sip|sr|Signature|X-Amz-Signature|X-Amz-Security-Token|X-Amz-Credential)=([^&\s]*)"
)
_AWS_SIGNED_URL_RE = re.compile(
    r"(?i)([?&])(X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token|Signature)=([^&\s]*)"
)


def _redact_query_value(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}={REDACTED}"


_PATTERNS: list[tuple[re.Pattern[str], str | None]] = [
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*"), f"Bearer {REDACTED}"),
    (re.compile(r"\bsk-(?:ant|proj|or-v1)-[A-Za-z0-9\-_]{8,}"), REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), REDACTED),
    (re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+"), f"password={REDACTED}"),
    (
        re.compile(r"(?i)(access_token|refresh_token|api_key|authorization)\s*[=:]\s*\S+"),
        REDACTED,
    ),
    (re.compile(r"(?i)(sharedaccesssignature|sas[_-]?token)\s*[=:]\s*\S+"), REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), REDACTED),
    (re.compile(r"(?i)(Server=|UID=|PWD=|Password=)[^;]+"), REDACTED),
]


def redact_secrets_in_text(value: str | None) -> str:
    if not value:
        return ""
    out = value
    out = _SAS_QUERY_RE.sub(_redact_query_value, out)
    out = _AWS_SIGNED_URL_RE.sub(_redact_query_value, out)
    for pat, repl in _PATTERNS:
        if repl is None:
            out = pat.sub(REDACTED, out)
        else:
            out = pat.sub(repl, out)
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
            if _SAFE_TOKEN_METRIC_KEY_RE.search(key):
                out[key] = redact_secrets_in_value(v, _depth=_depth + 1)
            elif _SENSITIVE_KEY_RE.search(key):
                out[key] = REDACTED
            else:
                out[key] = redact_secrets_in_value(v, _depth=_depth + 1)
        return out
    return redact_secrets_in_text(str(value))
