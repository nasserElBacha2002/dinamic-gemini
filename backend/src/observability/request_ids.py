"""Phase 5 — request / correlation ID validation and generation."""

from __future__ import annotations

import re
import uuid

# Safe printable id: alnum, dash, underscore. Reject arbitrary long / injection-prone values.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_LEN = 128


def generate_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def generate_correlation_id() -> str:
    return f"corr_{uuid.uuid4().hex}"


def normalize_inbound_id(raw: str | None, *, fallback: str) -> str:
    """Accept a valid inbound header or return a freshly generated fallback."""
    if raw is None:
        return fallback
    value = raw.strip()
    if not value or len(value) > _MAX_LEN or not _ID_RE.match(value):
        return fallback
    return value
