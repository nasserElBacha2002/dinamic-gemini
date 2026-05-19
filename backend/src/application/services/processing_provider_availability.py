"""Provider/model availability for aisle processing (test vs production modes)."""

from __future__ import annotations

from typing import Any, Literal

from src.application.errors import (
    InvalidProcessingModelError,
    ProcessingProviderNotConfiguredError,
    UnknownProcessingProviderError,
)
from src.application.services.processing_experiment_catalog import (
    default_model_for_provider,
    default_prompt_key,
    models_for_provider,
    prompt_profile_catalog,
)
from src.domain.inventory.entities import Inventory
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE
from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.providers.definitions import (
    PIPELINE_PROVIDER_SPECS,
    PipelineProviderSpec,
    credential_configured,
    pipeline_provider_spec,
    registered_pipeline_provider_keys_from_definitions,
)

ProcessingOptionsMode = Literal["test", "production"]


def _multimodal_aisle_analysis_supported(provider_key: str) -> bool:
    return provider_key.strip().lower() != "deepseek"


def production_default_model_id(provider_key: str, settings: Any) -> str | None:
    """Configured default production model (env attr), not the test model list."""
    spec = pipeline_provider_spec(provider_key)
    if spec is None:
        return None
    raw_dm = getattr(settings, spec.default_model_settings_attr, None)
    dm = (
        str(raw_dm).strip()
        if raw_dm is not None and str(raw_dm).strip()
        else spec.default_model_fallback
    )
    return dm or None


def production_provider_unavailable_reason(spec: PipelineProviderSpec, settings: Any) -> str | None:
    if not credential_configured(spec, settings):
        return spec.credential_missing_message
    if not _multimodal_aisle_analysis_supported(spec.key):
        return (
            f"{spec.label} is not available for vision-based aisle analysis in production mode."
        )
    if not production_default_model_id(spec.key, settings):
        return f"{spec.label} has no default production model configured."
    return None


def production_provider_catalog(settings: Any) -> dict[str, str]:
    """Map provider key → sole production model id for providers that are production-ready."""
    out: dict[str, str] = {}
    for spec in PIPELINE_PROVIDER_SPECS:
        reason = production_provider_unavailable_reason(spec, settings)
        if reason is not None:
            continue
        model_id = production_default_model_id(spec.key, settings)
        if model_id:
            out[spec.key] = model_id
    return out


def build_processing_provider_options_payload(
    settings: Any,
    *,
    mode: ProcessingOptionsMode,
) -> dict[str, Any]:
    """Structured payload for GET processing-provider-options (caller maps to Pydantic)."""
    default_provider = normalize_pipeline_provider_key(None, settings)
    default_prompt = default_prompt_key(settings)
    prompt_profiles = [
        {"key": k, "label": lab, "description": desc} for k, lab, desc in prompt_profile_catalog()
    ]

    if mode == "production":
        catalog = production_provider_catalog(settings)
        providers_out: list[dict[str, Any]] = []
        for spec in sorted(PIPELINE_PROVIDER_SPECS, key=lambda s: s.key):
            model_id = catalog.get(spec.key)
            if model_id is None:
                continue
            providers_out.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "execution_mode": "native",
                    "description": spec.description,
                    "models": [{"id": model_id, "label": model_id}],
                    "default_model": model_id,
                    "production_available": True,
                    "unavailable_reason": None,
                    "is_default_provider": spec.key == default_provider,
                }
            )
        default_model = catalog.get(default_provider) or (
            catalog.get(providers_out[0]["key"]) if providers_out else None
        )
        return {
            "mode": mode,
            "default_provider_key": default_provider,
            "default_model_key": default_model,
            "default_prompt_key": default_prompt,
            "prompt_profiles": prompt_profiles,
            "providers": providers_out,
        }

    providers_out = []
    for spec in sorted(PIPELINE_PROVIDER_SPECS, key=lambda s: s.key):
        pairs = models_for_provider(spec.key, settings)
        dm = default_model_for_provider(spec.key, settings)
        unavailable = production_provider_unavailable_reason(spec, settings)
        providers_out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "execution_mode": "native",
                "description": spec.description,
                "models": [{"id": m, "label": lab} for m, lab in pairs],
                "default_model": dm,
                "production_available": unavailable is None,
                "unavailable_reason": unavailable,
                "is_default_provider": spec.key == default_provider,
            }
        )
    default_model = default_model_for_provider(default_provider, settings)
    return {
        "mode": mode,
        "default_provider_key": default_provider,
        "default_model_key": default_model,
        "default_prompt_key": default_prompt,
        "prompt_profiles": prompt_profiles,
        "providers": providers_out,
    }


def resolve_production_processing_keys(
    inventory: Inventory,
    *,
    requested_provider_name: str | None,
    requested_model_name: str | None,
    settings: Any,
) -> tuple[str, str, str]:
    """Resolve provider/model for a production inventory process request.

    Provider: explicit request when production-ready, else inventory primary snapshot,
    else ``settings.llm_provider``, else first available production provider.
    Model: must match the provider's configured default production model when explicit.
    Prompt: always ``global_v22`` (operational label-first profile).
    """
    catalog = production_provider_catalog(settings)
    if not catalog:
        raise ProcessingProviderNotConfiguredError(
            "No production pipeline providers are configured (credentials and default models required)."
        )

    default_provider = normalize_pipeline_provider_key(None, settings)
    req_p = (requested_provider_name or "").strip().lower()
    inv_p = (inventory.primary_provider_name or "").strip().lower()

    if req_p:
        if req_p not in registered_pipeline_provider_keys_from_definitions():
            known = sorted(registered_pipeline_provider_keys_from_definitions())
            raise UnknownProcessingProviderError(
                f"Unknown processing provider {req_p!r}. Known keys: {known}"
            )
        if req_p not in catalog:
            spec = pipeline_provider_spec(req_p)
            msg = (
                production_provider_unavailable_reason(spec, settings)
                if spec is not None
                else f"Provider {req_p!r} is not available in production mode."
            )
            raise ProcessingProviderNotConfiguredError(msg or f"Provider {req_p!r} is not available.")
        provider = req_p
    elif inv_p and inv_p in catalog:
        provider = inv_p
    elif default_provider in catalog:
        provider = default_provider
    else:
        provider = sorted(catalog.keys())[0]

    allowed_model = catalog[provider]
    req_m = (requested_model_name or "").strip()
    if req_m:
        if req_m != allowed_model:
            raise InvalidProcessingModelError(
                f"Model {req_m!r} is not the production default for provider {provider!r}. "
                f"Allowed: [{allowed_model!r}]"
            )
        model = req_m
    else:
        model = allowed_model

    return provider, model, DEFAULT_HYBRID_PROMPT_PROFILE
