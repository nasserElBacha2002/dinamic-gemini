"""Provider/model availability for aisle processing (test vs production modes)."""

from __future__ import annotations

from typing import Any, Literal

from src.application.errors import (
    DeprecatedProcessingProviderError,
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
    deprecated_processing_provider_message,
    is_pipeline_provider_active,
    pipeline_provider_spec,
    registered_active_pipeline_provider_keys_from_definitions,
    registered_pipeline_provider_keys_from_definitions,
)

ProcessingOptionsMode = Literal["test", "production"]


def explicit_production_default_model_id(provider_key: str, settings: Any) -> str | None:
    """Production model id from explicit env only (e.g. GEMINI_MODEL_NAME, OPENAI_MODEL).

    Does **not** use ``PipelineProviderSpec.default_model_fallback``. Test-mode catalog
    (``models_for_provider`` / ``default_model_for_provider``) may still use fallbacks.
    """
    spec = pipeline_provider_spec(provider_key)
    if spec is None:
        return None
    raw_dm = getattr(settings, spec.default_model_settings_attr, None)
    if raw_dm is None:
        return None
    dm = str(raw_dm).strip()
    return dm or None


def production_provider_unavailable_reason(spec: PipelineProviderSpec, settings: Any) -> str | None:
    if not spec.is_active:
        return deprecated_processing_provider_message(spec.key)
    if not credential_configured(spec, settings):
        return spec.credential_missing_message
    if not explicit_production_default_model_id(spec.key, settings):
        return (
            f"{spec.label} has no explicit default production model configured "
            f"({spec.default_model_settings_attr})."
        )
    return None


def production_provider_catalog(settings: Any) -> dict[str, str]:
    """Map provider key → sole production model id for providers that are production-ready."""
    out: dict[str, str] = {}
    for spec in PIPELINE_PROVIDER_SPECS:
        if not spec.is_active:
            continue
        reason = production_provider_unavailable_reason(spec, settings)
        if reason is not None:
            continue
        model_id = explicit_production_default_model_id(spec.key, settings)
        if model_id:
            out[spec.key] = model_id
    return out


def effective_production_default_provider_key(
    settings: Any,
    catalog: dict[str, str],
) -> tuple[str, str | None]:
    """Return ``(default_provider_key, default_model_key)`` for production options.

  - When ``catalog`` is non-empty: use configured ``LLM_PROVIDER`` if production-ready,
    otherwise the first available production provider (sorted by key).
  - When ``catalog`` is empty: return normalized configured provider and ``None`` model.
    """
    configured = normalize_pipeline_provider_key(None, settings)
    if not catalog:
        return configured, None
    if configured in catalog:
        effective = configured
    else:
        effective = sorted(catalog.keys())[0]
    return effective, catalog[effective]


def build_processing_provider_options_payload(
    settings: Any,
    *,
    mode: ProcessingOptionsMode,
) -> dict[str, Any]:
    """Structured payload for GET processing-provider-options (caller maps to Pydantic)."""
    configured_provider = normalize_pipeline_provider_key(None, settings)
    default_prompt = default_prompt_key(settings)
    prompt_profiles = [
        {"key": k, "label": lab, "description": desc} for k, lab, desc in prompt_profile_catalog()
    ]

    if mode == "production":
        catalog = production_provider_catalog(settings)
        effective_provider, default_model = effective_production_default_provider_key(
            settings, catalog
        )
        providers_out: list[dict[str, Any]] = []
        for spec in sorted(PIPELINE_PROVIDER_SPECS, key=lambda s: s.key):
            if not spec.is_active:
                continue
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
                    "is_default_provider": spec.key == effective_provider,
                }
            )
        return {
            "mode": mode,
            "default_provider_key": effective_provider,
            "default_model_key": default_model,
            "default_prompt_key": default_prompt,
            "prompt_profiles": prompt_profiles,
            "providers": providers_out,
        }

    providers_out = []
    for spec in sorted(PIPELINE_PROVIDER_SPECS, key=lambda s: s.key):
        if not spec.is_active:
            continue
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
                "is_default_provider": spec.key == configured_provider,
            }
        )
    default_model = default_model_for_provider(configured_provider, settings)
    return {
        "mode": mode,
        "default_provider_key": configured_provider,
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

    **Production execution policy**

    * **Provider** (no explicit request): use inventory ``primary_provider_name`` when
      production-ready; otherwise the effective production default (same rules as
      ``effective_production_default_provider_key``).
    * **Model** (no explicit request): always the **current** explicit production default
      from env for the resolved provider (``explicit_production_default_model_id``).
      Inventory ``primary_model_name`` is not used for execution — operators may change
      env defaults without re-creating inventories.
    * **Model** (explicit request): must equal the provider's current production default.
    * **Prompt**: always ``global_v22`` (label-first operational profile).
    """
    catalog = production_provider_catalog(settings)
    if not catalog:
        raise ProcessingProviderNotConfiguredError(
            "No production pipeline providers are configured (credentials and default models required)."
        )

    effective_default, _ = effective_production_default_provider_key(settings, catalog)
    req_p = (requested_provider_name or "").strip().lower()
    inv_p = (inventory.primary_provider_name or "").strip().lower()

    if req_p:
        if not is_pipeline_provider_active(req_p):
            if req_p in registered_pipeline_provider_keys_from_definitions():
                raise DeprecatedProcessingProviderError(
                    deprecated_processing_provider_message(req_p)
                )
            known = sorted(registered_active_pipeline_provider_keys_from_definitions())
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
    elif effective_default in catalog:
        provider = effective_default
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
