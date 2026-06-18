"""
Central pipeline provider definitions (pre-Phase 10).

Single source for: registry keys, processing catalog field names, credential checks, capability
specs, and API labels. Adding a provider should start here, then wire ``resolve_llm_executor``
(adapter factory).

This is **not** a plugin framework — only declarative metadata to reduce drift between registry,
``processing_experiment_catalog``, ``processing_provider_resolution``, and API option text.

**Provider contract (Phase 5):** capabilities in :mod:`src.pipeline.providers.capabilities` are
authoritative for visual-inventory job compatibility. Runtime failover between vendors is **not**
implemented unless ``pipeline_analysis_execution_strategy`` enables multi-provider fallback in settings.

**Checklist when adding a provider:** (1) append a ``PipelineProviderSpec`` here; (2) declare
capabilities in ``capabilities.py``; (3) register an adapter factory in ``registry.py``; (4) run tests
that assert definition keys match the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from src.pipeline.providers.capabilities import (
    ProviderCapabilitySpec,
    pipeline_provider_capabilities,
)


@dataclass(frozen=True)
class PipelineProviderSpec:
    """Static metadata for one registered hybrid LLM provider."""

    key: str
    label: str
    description: str
    credential_settings_attr: str
    credential_missing_message: str
    processing_models_settings_attr: str
    default_model_settings_attr: str
    default_model_fallback: str
    is_active: bool = True

    @property
    def capabilities(self) -> ProviderCapabilitySpec | None:
        """Declared capabilities for this provider (Phase 5 contract)."""
        return pipeline_provider_capabilities(self.key)


PIPELINE_PROVIDER_SPECS: Final[tuple[PipelineProviderSpec, ...]] = (
    PipelineProviderSpec(
        key="gemini",
        label="Gemini",
        description="Native Gemini SDK path (GEMINI_API_KEY required when explicitly selected).",
        credential_settings_attr="gemini_api_key",
        credential_missing_message="Gemini is not configured (GEMINI_API_KEY is missing).",
        processing_models_settings_attr="processing_gemini_models",
        default_model_settings_attr="gemini_model_name",
        default_model_fallback="gemini-2.0-flash-exp",
    ),
    PipelineProviderSpec(
        key="openai",
        label="OpenAI",
        description="Native OpenAI vision path (Chat Completions + json_object). OPENAI_API_KEY required when explicitly selected.",
        credential_settings_attr="openai_api_key",
        credential_missing_message="OpenAI is not configured (OPENAI_API_KEY is missing).",
        processing_models_settings_attr="processing_openai_models",
        default_model_settings_attr="openai_model",
        default_model_fallback="gpt-4o",
    ),
    PipelineProviderSpec(
        key="claude",
        label="Claude",
        description="Native Anthropic Claude path (Messages API + vision). ANTHROPIC_API_KEY required when explicitly selected.",
        credential_settings_attr="anthropic_api_key",
        credential_missing_message="Claude is not configured (ANTHROPIC_API_KEY is missing).",
        processing_models_settings_attr="processing_claude_models",
        default_model_settings_attr="anthropic_model",
        default_model_fallback="claude-sonnet-4-20250514",
    ),
    PipelineProviderSpec(
        key="deepseek",
        label="DeepSeek",
        description=(
            "Legacy provider (deprecated). Retained for historical jobs and execution logs only; "
            "not selectable for new aisle processing."
        ),
        credential_settings_attr="deepseek_api_key",
        credential_missing_message="DeepSeek is not configured (DEEPSEEK_API_KEY is missing).",
        processing_models_settings_attr="processing_deepseek_models",
        default_model_settings_attr="deepseek_model",
        default_model_fallback="deepseek-chat",
        is_active=False,
    ),
)

_SPECS_BY_KEY: Final[dict[str, PipelineProviderSpec]] = {s.key: s for s in PIPELINE_PROVIDER_SPECS}


def pipeline_provider_spec(key: str) -> PipelineProviderSpec | None:
    return _SPECS_BY_KEY.get((key or "").strip().lower())


def registered_pipeline_provider_keys_from_definitions() -> frozenset[str]:
    """All registered pipeline provider keys (active + legacy; must match registry)."""
    return frozenset(_SPECS_BY_KEY.keys())


def registered_active_pipeline_provider_keys_from_definitions() -> frozenset[str]:
    """Keys selectable for new processing (API options, POST /process, supplier prompt configs)."""
    return frozenset(s.key for s in PIPELINE_PROVIDER_SPECS if s.is_active)


def is_pipeline_provider_active(key: str) -> bool:
    spec = pipeline_provider_spec(key)
    return spec is not None and spec.is_active


def deprecated_processing_provider_message(key: str) -> str:
    spec = pipeline_provider_spec(key)
    label = spec.label if spec is not None else key
    return (
        f"Provider {key!r} ({label}) is deprecated and can no longer be used for new executions."
    )


def credential_configured(spec: PipelineProviderSpec, settings: Any) -> bool:
    return bool((getattr(settings, spec.credential_settings_attr, "") or "").strip())
