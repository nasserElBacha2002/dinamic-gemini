"""
Phase 5 — provider contract validation for visual inventory (aisle) processing.

Visual inventory jobs require ``supports_vision`` and ``supports_image_binding`` on the selected
provider and model. Validation runs at job creation and defensively at worker execution resolution.

**Not runtime failover:** rejecting an incompatible provider does not switch to another vendor.
"""

from __future__ import annotations

from src.application.errors import ProcessingProviderIncompatibleWithJobError
from src.pipeline.provider_keys import (
    InactivePipelineProviderKeyError,
    ResolvedPipelineProviderKey,
    UnknownPipelineProviderKeyError,
    resolve_pipeline_provider_key,
)
from src.pipeline.providers.capabilities import (
    model_supports_visual_inventory,
    pipeline_provider_capabilities,
    provider_supports_visual_inventory,
)
from src.pipeline.providers.definitions import (
    deprecated_processing_provider_message,
    pipeline_provider_spec,
    registered_active_pipeline_provider_keys_from_definitions,
)

VISUAL_INVENTORY_JOB_KIND = "visual_inventory"


def _incompatible_provider_message(provider_key: str) -> str:
    spec = pipeline_provider_spec(provider_key)
    label = spec.label if spec is not None else provider_key
    if pipeline_provider_capabilities(provider_key) is None:
        return (
            f"Provider {provider_key!r} has no declared capability spec and cannot be used "
            f"for visual inventory processing."
        )
    return (
        f"Provider {provider_key!r} ({label}) does not support visual inventory processing "
        f"(requires vision and image binding). Select a compatible provider such as "
        f"gemini, openai, or claude."
    )


def _incompatible_model_message(provider_key: str, model_name: str) -> str:
    spec = pipeline_provider_spec(provider_key)
    label = spec.label if spec is not None else provider_key
    return (
        f"Model {model_name!r} is not compatible with visual inventory processing for "
        f"provider {provider_key!r} ({label})."
    )


def validate_provider_for_visual_inventory_job(provider_key: str) -> None:
    """
    Raise :class:`ProcessingProviderIncompatibleWithJobError` when provider capabilities are insufficient.
    """
    key = (provider_key or "").strip().lower()
    if not provider_supports_visual_inventory(key):
        raise ProcessingProviderIncompatibleWithJobError(
            _incompatible_provider_message(key),
            provider_key=key,
            job_kind=VISUAL_INVENTORY_JOB_KIND,
        )


def validate_provider_model_for_visual_inventory_job(
    provider_key: str,
    model_name: str | None,
) -> None:
    """Validate provider + optional model for visual inventory jobs (fail closed)."""
    key = (provider_key or "").strip().lower()
    validate_provider_for_visual_inventory_job(key)
    raw_model = (model_name or "").strip()
    if raw_model and not model_supports_visual_inventory(key, raw_model):
        raise ProcessingProviderIncompatibleWithJobError(
            _incompatible_model_message(key, raw_model),
            provider_key=key,
            model_name=raw_model,
            job_kind=VISUAL_INVENTORY_JOB_KIND,
        )


def validate_ordered_providers_for_visual_inventory_job(
    provider_keys: list[str],
    *,
    model_name: str | None,
) -> None:
    """Fail closed when any provider in a multi-provider list is incompatible with visual jobs."""
    for key in provider_keys:
        validate_provider_model_for_visual_inventory_job(key, model_name)


def resolve_and_validate_pipeline_provider_for_visual_job(
    provider_name: str | None,
    settings: object,
    *,
    model_name: str | None = None,
) -> ResolvedPipelineProviderKey:
    """
    Resolve provider key (fail-closed on explicit inactive/unknown) and validate visual capabilities.
    """
    try:
        resolved = resolve_pipeline_provider_key(provider_name, settings)
    except UnknownPipelineProviderKeyError as exc:
        known = sorted(registered_active_pipeline_provider_keys_from_definitions())
        raise ProcessingProviderIncompatibleWithJobError(
            f"Unknown processing provider {provider_name!r}. Known active keys: {known}",
            provider_key=(provider_name or "").strip().lower() or None,
            job_kind=VISUAL_INVENTORY_JOB_KIND,
        ) from exc
    except InactivePipelineProviderKeyError as exc:
        key = (provider_name or "").strip().lower()
        msg = deprecated_processing_provider_message(key) if key else str(exc)
        raise ProcessingProviderIncompatibleWithJobError(
            msg,
            provider_key=key or None,
            job_kind=VISUAL_INVENTORY_JOB_KIND,
        ) from exc

    if resolved.remapped:
        raise ProcessingProviderIncompatibleWithJobError(
            (
                f"Explicit provider {resolved.requested_key!r} cannot be remapped to "
                f"{resolved.resolved_key!r} for job execution."
            ),
            provider_key=resolved.requested_key,
            resolved_provider_key=resolved.resolved_key,
            job_kind=VISUAL_INVENTORY_JOB_KIND,
        )

    validate_provider_model_for_visual_inventory_job(resolved.resolved_key, model_name)
    return resolved
