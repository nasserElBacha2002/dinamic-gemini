"""Resolve and validate explicit processing selection: provider, model, prompt (Phase 5)."""

from __future__ import annotations

from typing import Any, Optional

from src.application.errors import (
    InvalidProcessingModelError,
    InvalidProcessingPromptKeyError,
    ProcessingProviderNotConfiguredError,
    UnknownProcessingProviderError,
)
from src.application.services.processing_experiment_catalog import (
    default_prompt_key,
    is_valid_prompt_key,
    models_for_provider,
    normalize_requested_model,
)
from src.llm.prompt_composer.hybrid_resolution import registered_hybrid_prompt_keys
from src.pipeline.providers.definitions import (
    credential_configured,
    pipeline_provider_spec,
    registered_pipeline_provider_keys_from_definitions,
)
from src.pipeline.provider_keys import normalize_pipeline_provider_key


def resolve_start_processing_request(
    *,
    requested_provider_name: Optional[str],
    requested_model_name: Optional[str],
    requested_prompt_key: Optional[str],
    settings: Any,
) -> tuple[str, Optional[str], str]:
    """
    Return ``(pipeline_provider_key, model_name, prompt_key)`` for a new process-aisle job.

    * Provider: same rules as before — empty → ``normalize_pipeline_provider_key(None, settings)``
      without credential gate; explicit → registered keys + credential check per vendor.
    * Model: empty → provider default from settings/catalog; explicit → must be in catalog for provider.
    * Prompt: empty → ``default_prompt_key(settings)`` (usually HYBRID_PROMPT); explicit → registered hybrid key.
    """
    raw_p = (requested_provider_name or "").strip()
    if not raw_p:
        provider_key = normalize_pipeline_provider_key(None, settings)
    else:
        provider_key = raw_p.lower()
        known = registered_pipeline_provider_keys_from_definitions()
        if provider_key not in known:
            raise UnknownProcessingProviderError(
                f"Unknown processing provider {provider_key!r}. Known keys: {sorted(known)}"
            )
        _ensure_explicit_provider_configured(provider_key, settings)

    pk_raw = (requested_prompt_key or "").strip()
    if not pk_raw:
        prompt_key = default_prompt_key(settings)
    else:
        if not is_valid_prompt_key(pk_raw, settings):
            raise InvalidProcessingPromptKeyError(
                f"Unknown prompt profile {pk_raw!r}. Known keys: {sorted(registered_hybrid_prompt_keys())}"
            )
        prompt_key = pk_raw

    model_raw = (requested_model_name or "").strip()
    resolved_model = normalize_requested_model(provider_key, model_raw or None, settings)
    if model_raw and resolved_model is None:
        allowed = [m for m, _ in models_for_provider(provider_key, settings)]
        raise InvalidProcessingModelError(
            f"Model {model_raw!r} is not available for provider {provider_key!r}. "
            f"Allowed: {allowed}"
        )
    if resolved_model is None:
        # Misconfigured catalog (no models) — fail honestly
        raise InvalidProcessingModelError(
            f"No selectable models configured for provider {provider_key!r}."
        )

    return provider_key, resolved_model, prompt_key


def _ensure_explicit_provider_configured(key: str, settings: Any) -> None:
    spec = pipeline_provider_spec(key)
    if spec is None:
        return
    if not credential_configured(spec, settings):
        raise ProcessingProviderNotConfiguredError(spec.credential_missing_message)
