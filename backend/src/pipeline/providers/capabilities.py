"""
Phase 5 — explicit provider capability contract (authoritative for job compatibility).

Capabilities are declared per registered pipeline provider key and consumed by processing
resolution, worker execution guards, admin inspection, and tests.

**Runtime failover is not implemented here.** Multi-provider sequential fallback is a separate
settings-driven strategy (``pipeline_analysis_execution_strategy``); provider availability and
job compatibility are determined from these specs only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from src.llm.provider_error_taxonomy import (
    PROVIDER_QUOTA_EXCEEDED,
    PROVIDER_RATE_LIMITED,
    PROVIDER_TIMEOUT,
)

# Global frame cap used when ``max_images`` is None (see FrameAcquisitionStage).
DEFAULT_VISUAL_JOB_MAX_IMAGES: Final[int] = 48


@dataclass(frozen=True)
class ProviderCapabilitySpec:
    """Declared capabilities for one hybrid LLM provider."""

    supports_vision: bool
    supports_json_mode: bool
    supports_structured_output: bool
    supports_image_binding: bool
    supports_cost_usage: bool
    supports_token_usage: bool
    #: Per-provider image cap; ``None`` means use ``DEFAULT_VISUAL_JOB_MAX_IMAGES``.
    max_images: int | None
    #: Soft limit for preflight warnings; ``None`` when not enforced.
    max_input_tokens: int | None
    #: Canonical error codes (see ``provider_error_taxonomy``) treated as retryable for this provider.
    retryable_errors: frozenset[str]


_GEMINI_CAPABILITIES = ProviderCapabilitySpec(
    supports_vision=True,
    supports_json_mode=True,
    supports_structured_output=True,
    supports_image_binding=True,
    supports_cost_usage=True,
    supports_token_usage=True,
    max_images=DEFAULT_VISUAL_JOB_MAX_IMAGES,
    max_input_tokens=None,
    retryable_errors=frozenset({PROVIDER_TIMEOUT, PROVIDER_RATE_LIMITED, PROVIDER_QUOTA_EXCEEDED}),
)

_OPENAI_CAPABILITIES = ProviderCapabilitySpec(
    supports_vision=True,
    supports_json_mode=True,
    supports_structured_output=False,
    supports_image_binding=True,
    supports_cost_usage=True,
    supports_token_usage=True,
    max_images=DEFAULT_VISUAL_JOB_MAX_IMAGES,
    max_input_tokens=None,
    retryable_errors=frozenset({PROVIDER_TIMEOUT, PROVIDER_RATE_LIMITED, PROVIDER_QUOTA_EXCEEDED}),
)

_CLAUDE_CAPABILITIES = ProviderCapabilitySpec(
    supports_vision=True,
    supports_json_mode=False,
    supports_structured_output=False,
    supports_image_binding=True,
    supports_cost_usage=True,
    supports_token_usage=True,
    max_images=DEFAULT_VISUAL_JOB_MAX_IMAGES,
    max_input_tokens=None,
    retryable_errors=frozenset({PROVIDER_TIMEOUT, PROVIDER_RATE_LIMITED, PROVIDER_QUOTA_EXCEEDED}),
)

_DEEPSEEK_CAPABILITIES = ProviderCapabilitySpec(
    supports_vision=False,
    supports_json_mode=True,
    supports_structured_output=False,
    supports_image_binding=False,
    supports_cost_usage=True,
    supports_token_usage=True,
    max_images=0,
    max_input_tokens=None,
    retryable_errors=frozenset({PROVIDER_TIMEOUT, PROVIDER_RATE_LIMITED}),
)

CAPABILITIES_BY_PROVIDER_KEY: Final[dict[str, ProviderCapabilitySpec]] = {
    "gemini": _GEMINI_CAPABILITIES,
    "openai": _OPENAI_CAPABILITIES,
    "claude": _CLAUDE_CAPABILITIES,
    "deepseek": _DEEPSEEK_CAPABILITIES,
}


def pipeline_provider_capabilities(provider_key: str) -> ProviderCapabilitySpec | None:
    return CAPABILITIES_BY_PROVIDER_KEY.get((provider_key or "").strip().lower())


def provider_supports_visual_inventory(provider_key: str) -> bool:
    """True when provider can run multimodal visual inventory (aisle photo/video) jobs."""
    caps = pipeline_provider_capabilities(provider_key)
    if caps is None:
        # Unknown / test doubles — defer to registry resolution; do not preflight here.
        return True
    return caps.supports_vision and caps.supports_image_binding


def assert_capabilities_registered_for_all_provider_keys(
    registered_keys: frozenset[str],
) -> None:
    """Test helper — every registry key must have a capability spec."""
    missing = registered_keys - frozenset(CAPABILITIES_BY_PROVIDER_KEY.keys())
    if missing:
        raise AssertionError(f"Missing capability specs for provider keys: {sorted(missing)}")
