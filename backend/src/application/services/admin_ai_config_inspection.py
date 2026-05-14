"""
Read-only snapshot of pipeline LLM / prompt configuration for admin inspection UI.

No secrets: never attach raw Settings or credential-bearing attributes to output dicts.

Payload is provider-centric. Composed prompt **text** is not included in the overview payload;
use ``compose_prompt_variant_for_inspection`` via GET ``/api/v3/admin/ai-config/composed-prompt``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Final, NamedTuple

from src.application.services.processing_experiment_catalog import (
    default_model_for_provider,
    models_for_provider,
    prompt_profile_catalog,
)
from src.config import Settings
from src.llm.normalization.entity_normalizer import (
    EXTRACTION_CONTRACT_VERSION_KEY,
    EXTRACTION_CONTRACT_VERSION_VALUE,
    resolve_provider_family,
)
from src.llm.prompt_composer.hybrid_assembly import (
    DEFAULT_HYBRID_PROMPT_PROFILE,
    compose_hybrid_base,
)
from src.llm.prompt_composer.hybrid_profiles import CLAUDE_JSON_ENTITY_OUTPUT_KEYS
from src.llm.prompt_composer.hybrid_resolution import registered_hybrid_prompt_keys
from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.providers.definitions import (
    PIPELINE_PROVIDER_SPECS,
    credential_configured,
    registered_pipeline_provider_keys_from_definitions,
)

_GLOBAL_INSTRUCTIONS_NOTE = (
    "Per-job operator instructions are not stored in server defaults. When an aisle run includes "
    "analysis context from the inventory, optional `instructions` strings are prepended to the "
    "hybrid prompt by the pipeline (before the composed base profile text). Visual reference "
    "images, when present, are attached as context images per provider adapter rules."
)

# Short provider-facing notes for the **instructions** section only (runtime / SDK behavior).
_PROVIDER_INSTRUCTION_NOTES: dict[str, str] = {
    "gemini": "Native Gemini SDK; hybrid base uses the `default` profile branch only.",
    "openai": "Chat Completions + vision; `openai` replacement fragment when parity mode is off.",
    "claude": "Anthropic Messages + vision; JSON entity contract supplement when parity mode is off.",
    "deepseek": "OpenAI-compatible Chat API; `default` branch only; multimodal aisle calls blocked in-adapter.",
}

_REQUIRED_ENTITY_KEYS_V21 = (
    "entity_type",
    "model_entity_id",
    "confidence",
    "has_boxes",
)

_OPTIONAL_NULLABLE_ENTITY_KEYS_V21 = tuple(
    k for k in CLAUDE_JSON_ENTITY_OUTPUT_KEYS if k not in _REQUIRED_ENTITY_KEYS_V21
)


class _ResponseContractRow(NamedTuple):
    wire_transport: str
    promotes_legacy_qty_bbox_aliases: bool
    claude_product_label_to_internal_code: bool
    transport_notes: tuple[str, ...]


_RESPONSE_CONTRACT_BY_PROVIDER: Final[dict[str, _ResponseContractRow]] = {
    "gemini": _ResponseContractRow(
        wire_transport="gemini_native_json",
        promotes_legacy_qty_bbox_aliases=True,
        claude_product_label_to_internal_code=False,
        transport_notes=(
            "JSON object after model output; validate_global_analysis_structure_v21 on parse.",
            "Gemini family may promote legacy qty/bbox aliases when canonical fields absent.",
        ),
    ),
    "openai": _ResponseContractRow(
        wire_transport="openai_chat_json_object",
        promotes_legacy_qty_bbox_aliases=False,
        claude_product_label_to_internal_code=False,
        transport_notes=(
            "response_format json_object; vision via image_url parts when frames exist.",
            "Normalization strips non-canonical keys (no blind qty/bbox promotion).",
        ),
    ),
    "claude": _ResponseContractRow(
        wire_transport="anthropic_messages_text_json",
        promotes_legacy_qty_bbox_aliases=False,
        claude_product_label_to_internal_code=True,
        transport_notes=(
            "Assistant message text parsed as JSON; hybrid adds contract supplement unless parity on.",
            "product_label → internal_code only when value matches SKU/code heuristic.",
        ),
    ),
    "deepseek": _ResponseContractRow(
        wire_transport="openai_compatible_json_object",
        promotes_legacy_qty_bbox_aliases=False,
        claude_product_label_to_internal_code=False,
        transport_notes=(
            "OpenAI-compatible client; JSON object mode for executed text-only calls.",
            "Multimodal aisle requests rejected before HTTP (UNSUPPORTED_MULTIMODAL_PROVIDER).",
        ),
    ),
}

_FALLBACK_RESPONSE_CONTRACT: Final[_ResponseContractRow] = _ResponseContractRow(
    wire_transport="unknown",
    promotes_legacy_qty_bbox_aliases=False,
    claude_product_label_to_internal_code=False,
    transport_notes=(
        "See validate_global_analysis_structure_v21 and entity_normalizer.",
    ),
)

_HYBRID_BASE_MODE_BY_PROVIDER: Final[dict[str, str]] = {
    "gemini": "default_profile_only",
    "deepseek": "default_profile_only",
    "openai": "openai_replacement_unless_parity",
    "claude": "default_plus_contract_supplement_unless_parity",
}

_DEFAULT_HYBRID_BASE_MODE: Final[str] = "default_profile_only"

_PARITY_AFFECTS_PROMPT_ASSEMBLY: Final[frozenset[str]] = frozenset({"openai", "claude"})

_MULTIMODAL_CONTEXT_POLICY_BY_PROVIDER: Final[dict[str, str]] = {
    "deepseek": "reject_images_before_http",
}
_DEFAULT_MULTIMODAL_CONTEXT_POLICY: Final[str] = "attach_when_adapter_supports_vision"


def _multimodal_supported(provider_key: str) -> bool:
    return provider_key.strip().lower() != "deepseek"


def _canonical_example_json() -> str:
    sample_entity = {
        "entity_type": "PALLET",
        "model_entity_id": "example_entity_1",
        "source_image_id": "frame_0",
        "confidence": 0.92,
        "has_boxes": True,
        "position_barcode": None,
        "internal_code": None,
        "position_label_bbox": None,
        "product_label_bbox": None,
        "product_label_quantity": None,
    }
    obj: dict[str, Any] = {
        EXTRACTION_CONTRACT_VERSION_KEY: EXTRACTION_CONTRACT_VERSION_VALUE,
        "total_entities_detected": 1,
        "entities": [sample_entity],
    }
    return json.dumps(obj, indent=2)


def _response_contract(provider_key: str) -> dict[str, Any]:
    """Structured contract metadata (minimal prose; UI can expand labels)."""
    fam = resolve_provider_family(provider_key)
    key = (provider_key or "").strip().lower()
    row = _RESPONSE_CONTRACT_BY_PROVIDER.get(key, _FALLBACK_RESPONSE_CONTRACT)
    promotes = row.promotes_legacy_qty_bbox_aliases

    return {
        "expects_json": True,
        "wire_transport": row.wire_transport,
        "validation_function": "validate_global_analysis_structure_v21",
        "normalization_function": "normalize_llm_response",
        "normalization_family": fam,
        "alias_promotion_policy": (
            "legacy_qty_bbox_when_canonical_absent_gemini_family"
            if promotes
            else "defensive_strip_no_blind_promotion"
        ),
        "claude_product_label_to_internal_code_when_valid": row.claude_product_label_to_internal_code,
        "required_root_keys": ["total_entities_detected", "entities"],
        "extra_root_keys_policy_short": (
            f"Extra root keys ignored by parser; optional {EXTRACTION_CONTRACT_VERSION_KEY} for audit."
        ),
        "required_entity_keys": list(_REQUIRED_ENTITY_KEYS_V21),
        "canonical_entity_keys": list(CLAUDE_JSON_ENTITY_OUTPUT_KEYS),
        "nullable_optional_entity_keys": list(_OPTIONAL_NULLABLE_ENTITY_KEYS_V21),
        "canonical_example_json": _canonical_example_json(),
        "transport_notes": list(row.transport_notes),
    }


def _composition_structured(provider_key: str) -> dict[str, Any]:
    """How hybrid base text is assembled — separate from operator instructions."""
    key = (provider_key or "").strip().lower()
    return {
        "hybrid_base_mode": _HYBRID_BASE_MODE_BY_PROVIDER.get(key, _DEFAULT_HYBRID_BASE_MODE),
        "parity_mode_affects_prompt_assembly": key in _PARITY_AFFECTS_PROMPT_ASSEMBLY,
        "multimodal_context_policy": _MULTIMODAL_CONTEXT_POLICY_BY_PROVIDER.get(
            key, _DEFAULT_MULTIMODAL_CONTEXT_POLICY
        ),
    }


def _safe_hybrid_prompt_key(settings: Any) -> str:
    """Readable hybrid profile key for admin UI; non-string settings values fall back to default."""
    raw = getattr(settings, "hybrid_prompt", None)
    if raw is None:
        return DEFAULT_HYBRID_PROMPT_PROFILE
    if not isinstance(raw, str):
        return DEFAULT_HYBRID_PROMPT_PROFILE
    stripped = raw.strip()
    return stripped or DEFAULT_HYBRID_PROMPT_PROFILE


def _prompt_catalog_rows_for_admin() -> list[dict[str, Any]]:
    """Catalog entries for UI: curated labels plus any registered hybrid keys missing from the catalog."""
    rows: list[dict[str, Any]] = [
        {"key": k, "label": lab, "description": desc} for k, lab, desc in prompt_profile_catalog()
    ]
    known = {r["key"] for r in rows}
    for k in sorted(registered_hybrid_prompt_keys()):
        if k not in known:
            rows.append(
                {
                    "key": k,
                    "label": k,
                    "description": "Hybrid profile registered in PROMPTS (no curated catalog blurb yet).",
                }
            )
    return rows


def iter_prompt_variant_summaries() -> list[dict[str, Any]]:
    """Metadata only — no composed prompt text (keeps overview payload small)."""
    reg_profiles = sorted(registered_hybrid_prompt_keys())
    reg_providers = sorted(registered_pipeline_provider_keys_from_definitions())
    out: list[dict[str, Any]] = []
    for pk in reg_profiles:
        for prov in reg_providers:
            parity_modes: list[bool] = [False]
            if prov == "openai":
                parity_modes.append(True)
            for parity in parity_modes:
                out.append(
                    {
                        "prompt_key": pk,
                        "pipeline_provider_key": prov,
                        "prompt_parity_mode": parity,
                        "variant_label": f"{pk} · {prov} · parity={parity}",
                    }
                )
    return out


def compose_prompt_variant_for_inspection(
    *,
    prompt_key: str,
    pipeline_provider_key: str,
    prompt_parity_mode: bool,
) -> dict[str, Any] | None:
    """
    On-demand composed prompt for admin inspection. Returns None if the tuple is not in the
    registered inspection matrix (same rules as variant summaries).
    """
    pk = prompt_key.strip()
    prov = pipeline_provider_key.strip().lower()
    allowed_profiles: set[str] = set(registered_hybrid_prompt_keys())
    allowed_providers = set(registered_pipeline_provider_keys_from_definitions())
    if pk not in allowed_profiles or prov not in allowed_providers:
        return None
    if prompt_parity_mode and prov != "openai":
        return None

    try:
        text = compose_hybrid_base(
            pk,
            prov,
            prompt_parity_mode=prompt_parity_mode,
            restrict_to_default_aisle_profile=False,
        )
    except Exception as exc:
        text = f"<composition error: {exc}>"
    label = f"{pk} · {prov} · parity={prompt_parity_mode}"
    return {
        "prompt_key": pk,
        "pipeline_provider_key": prov,
        "prompt_parity_mode": prompt_parity_mode,
        "variant_label": label,
        "composed_prompt_text": text,
    }


def build_admin_ai_config_payload(settings: Settings) -> dict[str, Any]:
    """Structured, secret-free payload for GET admin AI config (no composed prompt bodies)."""
    now = datetime.now(timezone.utc)
    default_pipeline = normalize_pipeline_provider_key(None, settings)
    hybrid_prompt = _safe_hybrid_prompt_key(settings)
    prompt_version = getattr(settings, "prompt_version", None)
    pv_opt = (
        prompt_version.strip()
        if isinstance(prompt_version, str) and prompt_version.strip()
        else None
    )

    summaries = iter_prompt_variant_summaries()
    variants_by_provider: dict[str, list[dict[str, Any]]] = {}
    for row in summaries:
        prov = row["pipeline_provider_key"]
        variants_by_provider.setdefault(prov, []).append(row)

    providers_out: list[dict[str, Any]] = []
    for spec in sorted(PIPELINE_PROVIDER_SPECS, key=lambda s: s.key):
        key = spec.key
        pairs = models_for_provider(key, settings)
        dm = default_model_for_provider(key, settings)
        cred = credential_configured(spec, settings)
        models_list = [{"id": mid, "label": lab, "is_default": mid == dm} for mid, lab in pairs]
        providers_out.append(
            {
                "key": key,
                "label": spec.label,
                "description": spec.description,
                "execution_mode": "native",
                "models": models_list,
                "default_model": dm,
                "capabilities": {
                    "is_default_pipeline_provider": key == default_pipeline,
                    "credential_configured": cred,
                    "multimodal_aisle_analysis_supported": _multimodal_supported(key),
                    "execution_mode": "native",
                },
                "instructions": {
                    "provider_specific_note": _PROVIDER_INSTRUCTION_NOTES.get(key, ""),
                },
                "response_contract": _response_contract(key),
                "composition": _composition_structured(key),
                "prompt_variant_summaries": variants_by_provider.get(key, []),
            }
        )

    prompt_catalog = _prompt_catalog_rows_for_admin()

    return {
        "generated_at": now.isoformat(),
        "server_defaults": {
            "llm_provider": str(getattr(settings, "llm_provider", "") or "").strip(),
            "hybrid_prompt_key": hybrid_prompt,
            "prompt_version": pv_opt,
        },
        "providers": providers_out,
        "prompt_catalog": prompt_catalog,
        "global_instructions_note": _GLOBAL_INSTRUCTIONS_NOTE,
    }
