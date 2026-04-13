"""
Read-only snapshot of pipeline LLM / prompt configuration for admin inspection UI.

No secrets: never attach raw Settings or credential-bearing attributes to output dicts.

Payload is provider-centric: each provider carries overview, instructions, response contract,
composition notes, and composed prompt variants for that provider only (no global variant dump).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

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
from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base
from src.llm.prompt_composer.hybrid_resolution import registered_hybrid_prompt_keys
from src.llm.prompt_composer.hybrid_profiles import CLAUDE_JSON_ENTITY_OUTPUT_KEYS
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

_PROVIDER_INSTRUCTION_NOTES: Dict[str, str] = {
    "gemini": "Uses native Gemini SDK; hybrid base text uses the `default` prompt branch only.",
    "openai": (
        "Uses Chat Completions + vision. When prompt parity mode is off, the `openai` replacement "
        "fragment replaces the default hybrid body for the selected profile."
    ),
    "claude": (
        "Uses Anthropic Messages API + vision. When prompt parity mode is off, the canonical "
        "JSON entity contract supplement is appended after the default hybrid body."
    ),
    "deepseek": (
        "Uses OpenAI-compatible client against DeepSeek Chat API. Hybrid base uses the `default` "
        "branch only. Multimodal image inputs are blocked in-adapter for aisle analysis until the "
        "hosted API supports them."
    ),
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
    obj: Dict[str, Any] = {
        EXTRACTION_CONTRACT_VERSION_KEY: EXTRACTION_CONTRACT_VERSION_VALUE,
        "total_entities_detected": 1,
        "entities": [sample_entity],
    }
    return json.dumps(obj, indent=2)


def _normalization_family_for_provider(provider_key: str) -> str:
    return resolve_provider_family(provider_key)


def _response_contract(provider_key: str) -> Dict[str, Any]:
    """Structured contract metadata for the admin UI (no runtime secrets)."""
    fam = _normalization_family_for_provider(provider_key)
    wire_notes: List[str] = []
    raw_expectation: str
    if provider_key == "gemini":
        raw_expectation = (
            "Assistant output is parsed as JSON (object). Gemini structured output is aligned "
            "with canonical v2.1 entity keys; legacy alias fields may appear and are handled in "
            "normalization only for the Gemini family."
        )
        wire_notes.append("Adapter validates with validate_global_analysis_structure_v21 after JSON parse.")
    elif provider_key == "openai":
        raw_expectation = (
            "Chat Completions API with response_format json_object: message content is one JSON "
            "object matching the hybrid prompt contract. OpenAI-specific key names outside the "
            "canonical set are stripped in normalization (no blind promotion of quantity/bbox aliases)."
        )
        wire_notes.append("Uses OpenAI SDK Chat Completions + vision image_url parts when frames exist.")
    elif provider_key == "claude":
        raw_expectation = (
            "Anthropic Messages API: assistant text is parsed as JSON. Prompt includes explicit "
            "canonical entity key list and forbidden keys; output should be a single JSON object."
        )
        wire_notes.append(
            "When prompt parity mode is off, the hybrid composer appends the Claude JSON entity "
            "contract supplement after the default base body."
        )
    elif provider_key == "deepseek":
        raw_expectation = (
            "OpenAI-compatible Chat Completions with JSON object mode when the request is executed. "
            "Aisle analysis with images is rejected before HTTP (multimodal unsupported for this vendor)."
        )
        wire_notes.append(
            "DeepSeek uses the same OpenAI-compatible JSON path as OpenAI for text-only requests; "
            "normalization family is deepseek (same defensive stripping policy as OpenAI for aliases)."
        )
    else:
        raw_expectation = "JSON object; validated after parse."
        wire_notes.append("See validate_global_analysis_structure_v21 and entity normalizer.")

    normalization_notes = [
        "Post-parse: normalize_llm_response (entity_normalizer) maps provider output into the "
        "canonical v2.1 entity shape before parse_entities / reporting.",
        f"Normalization family resolved as {fam!r} (from provider key {provider_key!r}).",
        "Gemini (and test_llm harness): may promote legacy quantity/bbox aliases into canonical fields "
        "when safe. OpenAI, DeepSeek, Claude: no blind alias promotion; some keys are stripped.",
        "Claude: product_label may map to internal_code when the string passes SKU/code heuristics; "
        "position_label is never mapped into position_barcode.",
    ]

    return {
        "expects_json": True,
        "validation_function": "validate_global_analysis_structure_v21",
        "normalization_function": "normalize_llm_response",
        "normalization_family": fam,
        "required_root_keys": ["total_entities_detected", "entities"],
        "extra_root_keys_policy": (
            "Additional root keys are allowed; parse_entities reads the canonical set. "
            f"{EXTRACTION_CONTRACT_VERSION_KEY} is optional metadata for audit."
        ),
        "required_entity_keys": list(_REQUIRED_ENTITY_KEYS_V21),
        "canonical_entity_keys": list(CLAUDE_JSON_ENTITY_OUTPUT_KEYS),
        "nullable_optional_entity_keys": list(_OPTIONAL_NULLABLE_ENTITY_KEYS_V21),
        "canonical_example_json": _canonical_example_json(),
        "raw_provider_expectation": raw_expectation,
        "canonical_contract_summary": (
            "Downstream code expects a v2.1 global analysis object: integer total_entities_detected, "
            "entities list, each entity with required keys above and optional fields nullable. "
            "After normalization every entity exposes the canonical key set used by parse_entities."
        ),
        "provider_wire_notes": wire_notes,
        "normalization_notes": normalization_notes,
    }


def _composition_notes(provider_key: str) -> Dict[str, Any]:
    spec_note = _PROVIDER_INSTRUCTION_NOTES.get(provider_key, "")
    hybrid_resolution = {
        "gemini": "Hybrid compose uses profile `default` branch only (no OpenAI replacement, no Claude supplement).",
        "openai": (
            "Default: `openai` replacement fragment replaces the default hybrid body for the profile. "
            "Prompt parity mode (per job): use the same `default` body as Gemini for A/B comparisons."
        ),
        "claude": (
            "Default: `default` hybrid body plus appended canonical JSON entity contract paragraph. "
            "Prompt parity mode: contract supplement omitted so the base matches Gemini-style experiments."
        ),
        "deepseek": "Hybrid compose uses profile `default` branch only (same resolution family as Gemini for base text).",
    }.get(provider_key, "See hybrid_resolution / compose_hybrid_base.")

    parity_detail = (
        "OpenAI and Claude respect per-job prompt_parity_mode from pipeline metadata. "
        "Gemini and DeepSeek are unaffected; they always use the default hybrid branch for base text."
    )

    multimodal_rules = (
        "Warehouse frames and optional inventory context images are attached per adapter capabilities."
        if _multimodal_supported(provider_key)
        else (
            "DeepSeek adapter rejects any request that includes frame or context images before calling "
            "the HTTP API (LLMProviderError UNSUPPORTED_MULTIMODAL_PROVIDER)."
        )
    )

    bullets = [
        hybrid_resolution,
        parity_detail,
        multimodal_rules,
        spec_note,
    ]

    return {
        "hybrid_base_resolution": hybrid_resolution,
        "parity_mode": parity_detail,
        "multimodal_context_rules": multimodal_rules,
        "provider_composition_summary": spec_note,
        "bullets": [b for b in bullets if b],
    }


def build_admin_ai_config_payload(settings: Settings) -> Dict[str, Any]:
    """Structured, secret-free payload for GET admin AI config."""
    now = datetime.now(timezone.utc)
    default_pipeline = normalize_pipeline_provider_key(None, settings)
    hybrid_prompt = str(getattr(settings, "hybrid_prompt", "") or "global_v21").strip()
    prompt_version = getattr(settings, "prompt_version", None)
    pv_opt = prompt_version.strip() if isinstance(prompt_version, str) and prompt_version.strip() else None

    reg_profiles = sorted(registered_hybrid_prompt_keys())
    reg_providers = sorted(registered_pipeline_provider_keys_from_definitions())

    all_variants: List[Dict[str, Any]] = []
    for pk in reg_profiles:
        for prov in reg_providers:
            parity_modes = [False]
            if prov == "openai":
                parity_modes.append(True)
            for parity in parity_modes:
                label = f"{pk} · {prov} · parity={parity}"
                try:
                    text = compose_hybrid_base(pk, prov, prompt_parity_mode=parity)
                except Exception as exc:  # noqa: BLE001 — inspection must stay stable
                    text = f"<composition error: {exc}>"
                all_variants.append(
                    {
                        "prompt_key": pk,
                        "pipeline_provider_key": prov,
                        "prompt_parity_mode": parity,
                        "variant_label": label,
                        "composed_prompt_text": text,
                    }
                )

    variants_by_provider: Dict[str, List[Dict[str, Any]]] = {p: [] for p in reg_providers}
    for v in all_variants:
        prov = v["pipeline_provider_key"]
        if prov in variants_by_provider:
            variants_by_provider[prov].append(v)

    providers_out: List[Dict[str, Any]] = []
    for spec in sorted(PIPELINE_PROVIDER_SPECS, key=lambda s: s.key):
        key = spec.key
        pairs = models_for_provider(key, settings)
        dm = default_model_for_provider(key, settings)
        cred = credential_configured(spec, settings)
        models_list = [
            {"id": mid, "label": lab, "is_default": mid == dm} for mid, lab in pairs
        ]
        providers_out.append(
            {
                "key": key,
                "label": spec.label,
                "description": spec.description,
                "execution_mode": "native",
                "models": models_list,
                "default_model": dm,
                "overview": {
                    "is_default_pipeline_provider": key == default_pipeline,
                    "credential_configured": cred,
                    "operationally_available": cred,
                    "multimodal_aisle_analysis_supported": _multimodal_supported(key),
                    "execution_mode": "native",
                },
                "instructions": {
                    "provider_specific_note": _PROVIDER_INSTRUCTION_NOTES.get(key, ""),
                },
                "response_contract": _response_contract(key),
                "composition_notes": _composition_notes(key),
                "prompt_variants": variants_by_provider.get(key, []),
            }
        )

    prompt_catalog = [
        {"key": k, "label": lab, "description": desc} for k, lab, desc in prompt_profile_catalog()
    ]

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
