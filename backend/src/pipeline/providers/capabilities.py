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

# Known text-only model ids (lowercase) that must not run visual inventory jobs per provider.
# Conservative denylist — unlisted catalog models for vision-capable providers are allowed.
KNOWN_TEXT_ONLY_MODEL_IDS_BY_PROVIDER: Final[dict[str, frozenset[str]]] = {
    "openai": frozenset(
        {
            "gpt-3.5-turbo",
            "gpt-4",
            "gpt-4-0314",
            "gpt-4-0613",
            "gpt-4-32k",
            "gpt-4-32k-0314",
            "gpt-4-32k-0613",
            "o1-preview",
            "o1-mini",
        }
    ),
    "claude": frozenset(),
    "gemini": frozenset(),
    "deepseek": frozenset({"deepseek-chat", "deepseek-reasoner", "deepseek-coder"}),
}

PROVIDER_CONTRACT_VERSION: Final[str] = "phase5.provider_contract.v1"


def pipeline_provider_capabilities(provider_key: str) -> ProviderCapabilitySpec | None:
    return CAPABILITIES_BY_PROVIDER_KEY.get((provider_key or "").strip().lower())


def provider_supports_visual_inventory(provider_key: str) -> bool:
    """True when provider has a declared capability spec supporting visual inventory jobs."""
    caps = pipeline_provider_capabilities(provider_key)
    if caps is None:
        return False
    return caps.supports_vision and caps.supports_image_binding


def model_supports_visual_inventory(provider_key: str, model_name: str | None) -> bool:
    """
    True when provider + model can run visual inventory jobs.

    Provider must have a capability spec. Models on the per-provider text-only denylist fail.
    Empty model_name skips model-level check (catalog validation handles missing models).
    """
    if not provider_supports_visual_inventory(provider_key):
        return False
    raw = (model_name or "").strip()
    if not raw:
        return True
    deny = KNOWN_TEXT_ONLY_MODEL_IDS_BY_PROVIDER.get((provider_key or "").strip().lower(), frozenset())
    return raw.lower() not in deny


def assert_capabilities_registered_for_all_provider_keys(
    registered_keys: frozenset[str],
) -> None:
    """Test helper — every registry key must have a capability spec."""
    missing = registered_keys - frozenset(CAPABILITIES_BY_PROVIDER_KEY.keys())
    if missing:
        raise AssertionError(f"Missing capability specs for provider keys: {sorted(missing)}")
