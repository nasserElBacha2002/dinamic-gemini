"""Phase 5 — canonical provider error taxonomy."""

from __future__ import annotations

import pytest

from src.llm.errors import LLMProviderError
from src.llm.provider_error_taxonomy import (
    PROVIDER_INCOMPATIBLE_WITH_JOB,
    PROVIDER_INVALID_RESPONSE,
    PROVIDER_JSON_PARSE_FAILED,
    PROVIDER_NOT_CONFIGURED,
    PROVIDER_RATE_LIMITED,
    PROVIDER_TIMEOUT,
    PROVIDER_UNKNOWN_ERROR,
    PROVIDER_VISION_NOT_SUPPORTED,
    canonical_provider_error_code,
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
    ],
)
def test_legacy_code_maps_to_canonical(legacy: str, canonical: str) -> None:
    assert canonical_provider_error_code(legacy) == canonical


def test_llm_provider_error_sets_canonical_and_retryable() -> None:
    exc = LLMProviderError("TIMEOUT", "timed out", details={"provider": "gemini"})
    assert exc.canonical_code == PROVIDER_TIMEOUT
    assert exc.retryable is True
    assert "PROVIDER_TIMEOUT" in str(exc)


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
