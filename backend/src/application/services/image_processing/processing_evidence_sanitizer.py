"""Phase 7 — sanitize processing evidence for PUBLIC_OPERATIONAL / TECHNICAL_SAFE views."""

from __future__ import annotations

from typing import Any


_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "bearer",
        "token",
        "prompt",
        "prompt_text",
        "raw_prompt",
        "full_text",
        "ocr_text",
        "payload",
        "raw_value",
        "stack_trace",
        "traceback",
        "worker_token",
        "storage_path",
        "absolute_path",
    }
)


def sanitize_metadata(
    raw: dict[str, Any] | None,
    *,
    level: str = "PUBLIC_OPERATIONAL",
) -> dict[str, Any]:
    """Strip secrets and optionally sensitive evidence fields."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        lk = str(key).strip().lower()
        if lk in _SENSITIVE_KEYS or lk.endswith("_api_key") or lk.endswith("_secret"):
            continue
        if level == "PUBLIC_OPERATIONAL" and lk in {
            "full_text_sha256",
            "request_image_sha256",
            "provider_response_sha256",
        }:
            # hashes are TECHNICAL_SAFE — keep for technical, drop for public if desired
            out[key] = value
            continue
        if isinstance(value, dict):
            out[key] = sanitize_metadata(value, level=level)
        elif isinstance(value, list):
            out[key] = [
                sanitize_metadata(v, level=level) if isinstance(v, dict) else v
                for v in value[:50]
            ]
        else:
            out[key] = value
    return out


def sanitize_attempt_view(attempt_dict: dict[str, Any]) -> dict[str, Any]:
    out = dict(attempt_dict)
    if isinstance(out.get("normalized_result"), dict):
        nr = dict(out["normalized_result"])
        nr.pop("full_text", None)
        nr.pop("raw_payload", None)
        out["normalized_result"] = nr
    if isinstance(out.get("extra"), dict):
        out["extra"] = sanitize_metadata(out["extra"])
    out.pop("worker_token", None)
    return out


__all__ = ["sanitize_attempt_view", "sanitize_metadata"]
