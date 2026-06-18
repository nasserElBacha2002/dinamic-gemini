"""Phase 5 — canonical provider error taxonomy."""

from __future__ import annotations

import pytest

from src.llm.errors import LLMProviderError
from src.llm.provider_error_taxonomy import (
    CANONICAL_PROVIDER_ERROR_CODES,
    PROVIDER_AUTH_FAILED,
    PROVIDER_CONTENT_BLOCKED,
    PROVIDER_INCOMPATIBLE_WITH_JOB,
    PROVIDER_INVALID_RESPONSE,
    PROVIDER_JSON_PARSE_FAILED,
    PROVIDER_MODEL_NOT_FOUND,
    PROVIDER_NOT_CONFIGURED,
    PROVIDER_QUOTA_EXCEEDED,
    PROVIDER_RATE_LIMITED,
    PROVIDER_TIMEOUT,
    PROVIDER_UNKNOWN_ERROR,
    PROVIDER_VISION_NOT_SUPPORTED,
    RESERVED_CANONICAL_PROVIDER_ERROR_CODES,
    canonical_provider_error_code,
    is_reserved_canonical_provider_error_code,
    provider_error_retryable,
)


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("TIMEOUT", PROVIDER_TIMEOUT),
        ("RATE_LIMIT", PROVIDER_RATE_LIMITED),
        ("PROVIDER_OVERLOADED", PROVIDER_RATE_LIMITED),
        ("NOT_CONFIGURED", PROVIDER_NOT_CONFIGURED),
        ("INVALID_JSON", PROVIDER_JSON_PARSE_FAILED),
        ("SCHEMA_INVALID", PROVIDER_INVALID_RESPONSE),
        ("UNKNOWN", PROVIDER_UNKNOWN_ERROR),
        ("UNSUPPORTED_MULTIMODAL_PROVIDER", PROVIDER_VISION_NOT_SUPPORTED),
        ("AUTH_FAILED", PROVIDER_AUTH_FAILED),
        ("INVALID_API_KEY", PROVIDER_AUTH_FAILED),
        ("MODEL_NOT_FOUND", PROVIDER_MODEL_NOT_FOUND),
        ("QUOTA_EXCEEDED", PROVIDER_QUOTA_EXCEEDED),
        ("CONTENT_BLOCKED", PROVIDER_CONTENT_BLOCKED),
        ("SAFETY_BLOCKED", PROVIDER_CONTENT_BLOCKED),
    ],
)
def test_legacy_code_maps_to_canonical(legacy: str, canonical: str) -> None:
    assert canonical_provider_error_code(legacy) == canonical


def test_unknown_legacy_maps_to_provider_unknown_error() -> None:
    assert canonical_provider_error_code("TOTALLY_UNKNOWN_LEGACY") == PROVIDER_UNKNOWN_ERROR


@pytest.mark.parametrize("code", sorted(CANONICAL_PROVIDER_ERROR_CODES))
def test_every_canonical_code_is_mapped_or_reserved(code: str) -> None:
    if code in RESERVED_CANONICAL_PROVIDER_ERROR_CODES:
        assert is_reserved_canonical_provider_error_code(code)
        return
    # Identity mapping or reachable via at least one legacy alias in parametrized tests above.
    assert canonical_provider_error_code(code) == code


def test_llm_provider_error_preserves_legacy_code_and_canonical() -> None:
    exc = LLMProviderError("TIMEOUT", "timed out", details={"provider": "gemini"})
    assert exc.code == "TIMEOUT"
    assert exc.canonical_code == PROVIDER_TIMEOUT
    assert exc.retryable is True
    assert "PROVIDER_TIMEOUT" in str(exc)
    assert "legacy_code=TIMEOUT" in str(exc)
    assert exc.details.get("legacy_code") == "TIMEOUT"


def test_llm_provider_error_canonical_code_only_string_when_no_legacy() -> None:
    exc = LLMProviderError(PROVIDER_INCOMPATIBLE_WITH_JOB, "bad provider")
    assert exc.code == PROVIDER_INCOMPATIBLE_WITH_JOB
    assert exc.canonical_code == PROVIDER_INCOMPATIBLE_WITH_JOB
    assert "legacy_code=" not in str(exc)


def test_auth_maps_to_not_configured_legacy() -> None:
    assert canonical_provider_error_code("NOT_CONFIGURED") == PROVIDER_NOT_CONFIGURED


def test_anthropic_retryable_class_in_details() -> None:
    exc = LLMProviderError(
        "PROVIDER_OVERLOADED",
        "overloaded",
        details={"provider": "claude", "retryable_class": True},
    )
    assert exc.canonical_code == PROVIDER_RATE_LIMITED
    assert exc.retryable is True


def test_incompatible_job_not_retryable() -> None:
    exc = LLMProviderError(PROVIDER_INCOMPATIBLE_WITH_JOB, "bad provider")
    assert exc.retryable is False


def test_provider_error_retryable_respects_capability_set() -> None:
    assert provider_error_retryable("RATE_LIMIT", provider_key="claude") is True


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (PROVIDER_TIMEOUT, True),
        (PROVIDER_RATE_LIMITED, True),
        (PROVIDER_QUOTA_EXCEEDED, True),
        (PROVIDER_AUTH_FAILED, False),
        (PROVIDER_INCOMPATIBLE_WITH_JOB, False),
        (PROVIDER_MODEL_NOT_FOUND, False),
    ],
)
def test_default_retryable_defaults(code: str, expected: bool) -> None:
    assert provider_error_retryable(code) is expected
