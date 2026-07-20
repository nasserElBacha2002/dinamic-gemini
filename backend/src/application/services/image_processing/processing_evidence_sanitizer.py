"""Phase 7 — allowlist sanitization by disclosure level."""

from __future__ import annotations

from typing import Any

PUBLIC_OPERATIONAL_KEYS = frozenset(
    {
        "id",
        "status",
        "strategy",
        "provider",
        "model",
        "prompt_key",
        "prompt_version",
        "error_code",
        "error_message",
        "duration_ms",
        "confidence",
        "estimated_cost",
        "attempt_number",
        "started_at",
        "finished_at",
        "internal_code",
        "quantity",
        "position_id",
        "active_result_id",
        "warnings",
        "event_type",
        "message",
        "severity",
        "timestamp",
        "resolved_by",
        "requested_mode",
        "executed_strategy",
        "persistence_status",
        "profile_key",
        "profile_version",
        "profile_source",
        "detection_count",
        "detected_format",
        "scanner",
        "engine",
        "language",
        "selected_variant",
        "text_block_count",
        # OCR / label-detection operational counters (no raw OCR text).
        "byte_length",
        "candidate_count",
        "selected",
        "variant",
        "psm",
        "failure_reason",
        "total_assets",
        "assets_eligible",
        "assets_skipped",
        "resolved",
        "unrecognized",
        "manual_review",
        "failed_technical",
        "pending",
        "cancelled",
        "numeric_token_count",
        "normalized_token_count",
        "configured_anchor_count",
        "exact_match_count",
        "fuzzy_match_count",
        "matched_anchor_count",
        "code_before_filter",
        "code_after_filter",
        "quantity_before_filter",
        "quantity_after_filter",
        "rejected_candidate_count",
        "code_candidates_after_filter",
        "raw_numeric_token_count",
        "masked_value",
        "length",
        "reason_code",
        "source",
        "field",
    }
)

TECHNICAL_SAFE_KEYS = PUBLIC_OPERATIONAL_KEYS | frozenset(
    {
        "request_image_sha256",
        "provider_response_sha256",
        "normalized_result_sha256",
        "full_text_sha256",
        "payload_hash",
        "correlation_id",
        "configuration_snapshot_version",
        "validation_result",
        "execution_scope",
        "variants_attempted",
        "variants_succeeded",
        "preprocessing_variant",
        "rotation",
        "region",
        "eligibility_reason",
        "retry_count",
        "circuit_breaker_state",
        # Label detection / geometry diagnostics (no image bytes or full OCR text).
        "selected_relative_area",
        "matched_anchors",
        "light_ocr_executed",
        "light_ocr_failed",
        "anchor_requirement_met",
        "anchor_match_policy",
        "deskew_applied",
        "perspective_transform_applied",
        "applied_rotation_deg",
        "used_original_region",
        "used_full_image_fallback",
        "successful_engine_call",
        "error_type",
        "validation_errors",
        "code_candidates_before_filter",
        "quantity_candidates_before_filter",
        "raw_alphanumeric_token_count",
        "extraction_method",
        "rejection_reasons",
        "exception_type",
        "safe_message",
        "stage",
        "code_candidates_count",
        "quantity_candidates_count",
        "status",
        "internal_code_status",
        "quantity_status",
    }
)

SENSITIVE_ADMIN_KEYS = TECHNICAL_SAFE_KEYS | frozenset(
    {
        "normalized_result",
        "code_candidates",
        "quantity_candidates",
        "selected_sources",
        "usage",
    }
)

_MAX_DEPTH = 6
_MAX_LIST = 50
_MAX_STRING = 500


def _allowed_keys(level: str) -> frozenset[str]:
    if level == "SENSITIVE_ADMIN":
        return SENSITIVE_ADMIN_KEYS
    if level == "TECHNICAL_SAFE":
        return TECHNICAL_SAFE_KEYS
    return PUBLIC_OPERATIONAL_KEYS


def sanitize_metadata(
    raw: dict[str, Any] | None,
    *,
    level: str = "PUBLIC_OPERATIONAL",
    _depth: int = 0,
) -> dict[str, Any]:
    if not isinstance(raw, dict) or _depth > _MAX_DEPTH:
        return {}
    allowed = _allowed_keys(level)
    out: dict[str, Any] = {}
    for key, value in raw.items():
        lk = str(key)
        if lk not in allowed and lk.lower() not in {a.lower() for a in allowed}:
            continue
        if lk == "rejection_reasons" and isinstance(value, dict):
            # Aggregated reason → count map (keys are reason codes, values ints).
            out[key] = {
                str(rk)[:80]: (int(rv) if isinstance(rv, (int, float)) else 0)
                for rk, rv in list(value.items())[:50]
            }
            continue
        out[key] = _sanitize_value(value, level=level, depth=_depth + 1)
    return out


def _sanitize_value(value: Any, *, level: str, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return None
    if isinstance(value, dict):
        return sanitize_metadata(value, level=level, _depth=depth)
    if isinstance(value, list):
        return [
            _sanitize_value(v, level=level, depth=depth + 1) for v in value[:_MAX_LIST]
        ]
    if isinstance(value, str):
        return value[:_MAX_STRING]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_STRING]


def sanitize_attempt_view(
    attempt_dict: dict[str, Any],
    *,
    level: str = "PUBLIC_OPERATIONAL",
) -> dict[str, Any]:
    base = {
        "id": attempt_dict.get("id"),
        "attempt_number": attempt_dict.get("attempt_number"),
        "strategy": attempt_dict.get("strategy"),
        "provider": attempt_dict.get("provider"),
        "model": attempt_dict.get("model"),
        "status": attempt_dict.get("status"),
        "started_at": attempt_dict.get("started_at"),
        "finished_at": attempt_dict.get("finished_at"),
        "duration_ms": attempt_dict.get("duration_ms"),
        "error_code": attempt_dict.get("error_code"),
        "error_message": attempt_dict.get("error_message"),
        "execution_scope": attempt_dict.get("execution_scope"),
    }
    nr = attempt_dict.get("normalized_result")
    if isinstance(nr, dict):
        base["normalized_result"] = sanitize_metadata(
            {
                "internal_code": nr.get("internal_code"),
                "quantity": nr.get("quantity"),
                "confidence": nr.get("confidence"),
            },
            level=level,
        )
    vr = attempt_dict.get("validation_result")
    if isinstance(vr, dict) and level != "PUBLIC_OPERATIONAL":
        base["validation_result"] = sanitize_metadata(vr, level=level)
    elif isinstance(vr, dict):
        warnings = vr.get("warnings")
        if isinstance(warnings, list):
            base["warnings"] = [str(w)[:200] for w in warnings[:20]]
    return {k: v for k, v in base.items() if v is not None}


def csv_safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text[:1] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


__all__ = [
    "PUBLIC_OPERATIONAL_KEYS",
    "TECHNICAL_SAFE_KEYS",
    "SENSITIVE_ADMIN_KEYS",
    "csv_safe_cell",
    "sanitize_attempt_view",
    "sanitize_metadata",
]
