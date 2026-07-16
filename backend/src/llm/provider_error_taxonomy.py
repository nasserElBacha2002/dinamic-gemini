"""
Phase 5 — canonical provider error taxonomy and legacy compatibility mapping.

Adapters may continue raising legacy ``LLMProviderError.code`` values; :class:`~src.llm.errors.LLMProviderError`
derives ``canonical_code`` and ``retryable`` from this module automatically.

**Runtime provider failover is not implemented.** Retryability here governs adapter-level retries and
operational classification only — not automatic vendor switching.
"""

from __future__ import annotations

from typing import Final

# Canonical codes (stable operational taxonomy).
PROVIDER_TIMEOUT: Final[str] = "PROVIDER_TIMEOUT"
PROVIDER_RATE_LIMITED: Final[str] = "PROVIDER_RATE_LIMITED"
PROVIDER_AUTH_FAILED: Final[str] = "PROVIDER_AUTH_FAILED"
PROVIDER_MODEL_NOT_FOUND: Final[str] = "PROVIDER_MODEL_NOT_FOUND"
PROVIDER_VISION_NOT_SUPPORTED: Final[str] = "PROVIDER_VISION_NOT_SUPPORTED"
PROVIDER_INVALID_RESPONSE: Final[str] = "PROVIDER_INVALID_RESPONSE"
PROVIDER_JSON_PARSE_FAILED: Final[str] = "PROVIDER_JSON_PARSE_FAILED"
PROVIDER_CONTENT_BLOCKED: Final[str] = "PROVIDER_CONTENT_BLOCKED"
PROVIDER_QUOTA_EXCEEDED: Final[str] = "PROVIDER_QUOTA_EXCEEDED"
PROVIDER_UNKNOWN_ERROR: Final[str] = "PROVIDER_UNKNOWN_ERROR"
PROVIDER_NOT_CONFIGURED: Final[str] = "PROVIDER_NOT_CONFIGURED"
PROVIDER_INCOMPATIBLE_WITH_JOB: Final[str] = "PROVIDER_INCOMPATIBLE_WITH_JOB"
PROVIDER_INVALID_REQUEST: Final[str] = "PROVIDER_INVALID_REQUEST"

# Canonical codes with no dedicated legacy adapter emitters yet (identity / direct raise only).
RESERVED_CANONICAL_PROVIDER_ERROR_CODES: Final[frozenset[str]] = frozenset()

CANONICAL_PROVIDER_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        PROVIDER_TIMEOUT,
        PROVIDER_RATE_LIMITED,
        PROVIDER_AUTH_FAILED,
        PROVIDER_MODEL_NOT_FOUND,
        PROVIDER_VISION_NOT_SUPPORTED,
        PROVIDER_INVALID_RESPONSE,
        PROVIDER_JSON_PARSE_FAILED,
        PROVIDER_CONTENT_BLOCKED,
        PROVIDER_QUOTA_EXCEEDED,
        PROVIDER_UNKNOWN_ERROR,
        PROVIDER_NOT_CONFIGURED,
        PROVIDER_INCOMPATIBLE_WITH_JOB,
        PROVIDER_INVALID_REQUEST,
    }
)

# Legacy adapter / pipeline codes → canonical.
_LEGACY_TO_CANONICAL: Final[dict[str, str]] = {
    "TIMEOUT": PROVIDER_TIMEOUT,
    "RATE_LIMIT": PROVIDER_RATE_LIMITED,
    "PROVIDER_OVERLOADED": PROVIDER_RATE_LIMITED,
    "NOT_CONFIGURED": PROVIDER_NOT_CONFIGURED,
    "INVALID_JSON": PROVIDER_JSON_PARSE_FAILED,
    "SCHEMA_INVALID": PROVIDER_INVALID_RESPONSE,
    "UNKNOWN": PROVIDER_UNKNOWN_ERROR,
    "NO_FRAMES": PROVIDER_INCOMPATIBLE_WITH_JOB,
    "UNSUPPORTED_MULTIMODAL_PROVIDER": PROVIDER_VISION_NOT_SUPPORTED,
    "PROVIDER_IMAGE_MANIFEST_MISMATCH": PROVIDER_INCOMPATIBLE_WITH_JOB,
    "PROVIDER_IMAGE_SERIALIZATION_FAILED": PROVIDER_INCOMPATIBLE_WITH_JOB,
    "PROVIDER_IMAGE_UNSUPPORTED_FORMAT": PROVIDER_INCOMPATIBLE_WITH_JOB,
    "PROVIDER_IMAGE_LIMIT_EXCEEDED": PROVIDER_INCOMPATIBLE_WITH_JOB,
    "PROVIDER_IMAGE_RESOURCE_MISSING": PROVIDER_INCOMPATIBLE_WITH_JOB,
    # Invalid payload / normalization — not "job incompatible with provider".
    "PROVIDER_IMAGE_DIMENSION_EXCEEDED": PROVIDER_INVALID_REQUEST,
    "PROVIDER_IMAGE_NORMALIZATION_FAILED": PROVIDER_INVALID_REQUEST,
    "PROVIDER_INVALID_MULTIMODAL_REQUEST": PROVIDER_INVALID_REQUEST,
    "PROVIDER_IMAGE_VALIDATION_FAILED": PROVIDER_INVALID_REQUEST,
    "AUTH_FAILED": PROVIDER_AUTH_FAILED,
    "INVALID_API_KEY": PROVIDER_AUTH_FAILED,
    "MODEL_NOT_FOUND": PROVIDER_MODEL_NOT_FOUND,
    "QUOTA_EXCEEDED": PROVIDER_QUOTA_EXCEEDED,
    "CONTENT_BLOCKED": PROVIDER_CONTENT_BLOCKED,
    "SAFETY_BLOCKED": PROVIDER_CONTENT_BLOCKED,
}

# Canonical codes retryable by default (adapter / worker policy may narrow per provider).
_DEFAULT_RETRYABLE_CANONICAL: Final[frozenset[str]] = frozenset(
    {
        PROVIDER_TIMEOUT,
        PROVIDER_RATE_LIMITED,
        PROVIDER_QUOTA_EXCEEDED,
    }
)


def canonical_provider_error_code(code: str) -> str:
    """Map legacy or canonical code to a canonical provider error code."""
    raw = (code or "").strip()
    if not raw:
        return PROVIDER_UNKNOWN_ERROR
    if raw in CANONICAL_PROVIDER_ERROR_CODES:
        return raw
    return _LEGACY_TO_CANONICAL.get(raw, PROVIDER_UNKNOWN_ERROR)


def provider_error_retryable(
    code: str,
    *,
    provider_key: str | None = None,
    details_retryable_class: bool | None = None,
) -> bool:
    """
    Whether an error with ``code`` (legacy or canonical) should be treated as retryable.

    ``details_retryable_class`` wins when set (e.g. Anthropic adapter classification).
    Otherwise uses provider capability ``retryable_errors`` when ``provider_key`` is known,
    then falls back to default retryable canonical set.
    """
    if details_retryable_class is not None:
        return bool(details_retryable_class)
    canonical = canonical_provider_error_code(code)
    if provider_key:
        from src.pipeline.providers.capabilities import pipeline_provider_capabilities

        caps = pipeline_provider_capabilities(provider_key)
        if caps is not None and canonical in caps.retryable_errors:
            return True
    return canonical in _DEFAULT_RETRYABLE_CANONICAL


def is_reserved_canonical_provider_error_code(code: str) -> bool:
    """True when canonical code is documented but not yet emitted by adapters."""
    return canonical_provider_error_code(code) in RESERVED_CANONICAL_PROVIDER_ERROR_CODES
