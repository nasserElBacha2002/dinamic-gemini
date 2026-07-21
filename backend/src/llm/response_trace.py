"""Safe provider-response trace metadata (hash/length only — never the body)."""

from __future__ import annotations

import hashlib
from typing import Any


def response_trace_metadata(
    *,
    raw_text: str | None,
    provider_request_id: str | None = None,
    provider_model: str | None = None,
    content_type: str | None = "text/plain",
) -> dict[str, Any]:
    text = raw_text if isinstance(raw_text, str) else ""
    meta: dict[str, Any] = {
        "provider_response_length": len(text),
        "provider_response_content_type": content_type,
    }
    if text:
        meta["provider_response_sha256"] = hashlib.sha256(
            text.encode("utf-8", errors="replace")
        ).hexdigest()
    if provider_request_id:
        meta["provider_request_id"] = str(provider_request_id)[:128]
    if provider_model:
        meta["provider_model"] = str(provider_model)[:128]
    return meta


__all__ = ["response_trace_metadata"]
