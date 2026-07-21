"""Phase 5 — versioned prompt for single-image external label analysis."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.llm.schema_versions import LlmSchemaVersion

EXTERNAL_FALLBACK_PROMPT_KEY = "external_fallback_single_label"
EXTERNAL_FALLBACK_PROMPT_VERSION = "1.0.0"
EXTERNAL_FALLBACK_COMPOSITION_VERSION = "1"

EXTERNAL_FALLBACK_PROMPT_TEXT = """[BASE]
You analyze exactly ONE inventory label image.

Rules (mandatory):
- This image represents at most ONE physical label / position.
- Return at most one internal_code and one quantity.
- Never invent a code or a quantity. If evidence is insufficient, say so.
- If multiple distinct labels/products are visible, mark the result as AMBIGUOUS.
- Do not default quantity to 1.
- Prefer explicit labeled fields over guessing.
"""

_OUTPUT_CONTRACT = f"""
[OUTPUT CONTRACT]
schema_version={LlmSchemaVersion.EXTERNAL_FALLBACK_V1}
Respond with ONLY valid JSON (no markdown) using this schema:
{{
  "status": "VALID" | "INVALID" | "AMBIGUOUS" | "NO_RESULT",
  "internal_code": string | null,
  "quantity": integer | null,
  "confidence": number | null,
  "warnings": string[],
  "reason": string | null
}}
Do NOT return hybrid aisle schemas (no "entities", no "total_entities_detected").
"""


def _client_rules_section(client_rules: dict[str, Any] | None) -> str | None:
    if not client_rules:
        return None
    lines = ["[CLIENT RULES]"]
    key = client_rules.get("client_rule_key")
    ver = client_rules.get("client_rule_version")
    if key:
        lines.append(f"- client_rule_key: {key}" + (f"@{ver}" if ver else ""))
    prefer = client_rules.get("prefer_ean_as_internal_code")
    if prefer is True:
        lines.append(
            "- When both EAN and an internal article code are present, prefer the EAN as internal_code."
        )
    elif prefer is False:
        lines.append(
            "- When both EAN and an internal article code are present, prefer the labeled "
            "internal article code over a bare EAN."
        )
    priority = client_rules.get("internal_code_priority")
    if isinstance(priority, list) and priority:
        lines.append("- internal_code priority: " + ", ".join(str(x) for x in priority[:12]))
    required = client_rules.get("required_fields")
    if isinstance(required, list) and required:
        lines.append("- required fields when status=VALID: " + ", ".join(str(x) for x in required))
    return "\n".join(lines) if len(lines) > 1 else None


def _supplier_profile_section(supplier_extraction_profile: dict[str, Any] | None) -> str | None:
    """Render non-sensitive supplier extraction profile hints for the LLM prompt."""
    if not isinstance(supplier_extraction_profile, dict) or not supplier_extraction_profile:
        return None
    lines = ["[SUPPLIER EXTRACTION PROFILE]"]
    for key in (
        "profile_key",
        "profile_version",
        "supplier_profile_id",
        "source",
    ):
        val = supplier_extraction_profile.get(key)
        if val is not None and str(val).strip():
            lines.append(f"- {key}: {str(val).strip()[:120]}")
    cfg = supplier_extraction_profile.get("configuration")
    if isinstance(cfg, dict):
        code_rules = cfg.get("code_validation") or cfg.get("code_rules")
        if isinstance(code_rules, dict):
            for rk in ("exact_length", "min_length", "max_length", "charset"):
                if code_rules.get(rk) is not None:
                    lines.append(f"- code.{rk}: {code_rules.get(rk)}")
        qty_rules = cfg.get("quantity_validation") or cfg.get("quantity_rules")
        if isinstance(qty_rules, dict):
            for rk in ("min", "max", "required"):
                if qty_rules.get(rk) is not None:
                    lines.append(f"- quantity.{rk}: {qty_rules.get(rk)}")
        anchors = cfg.get("label_anchors") or cfg.get("anchors")
        if isinstance(anchors, list) and anchors:
            safe = [str(a)[:40] for a in anchors[:8]]
            lines.append("- label anchors: " + ", ".join(safe))
        free_text = cfg.get("llm_instructions") or cfg.get("external_instructions")
        if isinstance(free_text, str) and free_text.strip():
            lines.append("- instructions:\n" + free_text.strip()[:1500])
    return "\n".join(lines) if len(lines) > 1 else None


def _runtime_section(
    *,
    quantity_max: int | None,
    strategy: str | None,
    required_fields: list[str] | None,
) -> str | None:
    lines = ["[RUNTIME CONTEXT]"]
    lines.append("- One image corresponds to one label attempt.")
    if quantity_max is not None:
        lines.append(f"- quantity_max: {int(quantity_max)}")
    if strategy:
        lines.append(f"- primary_strategy: {strategy}")
    if required_fields:
        lines.append("- required_fields_when_valid: " + ", ".join(required_fields))
    return "\n".join(lines)


def compose_external_fallback_prompt(
    *,
    client_rules: dict[str, Any] | None = None,
    supplier_extraction_profile: dict[str, Any] | None = None,
    quantity_max: int | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Compose the effective fallback prompt and return text + audit metadata."""
    required = None
    if isinstance(client_rules, dict):
        raw_req = client_rules.get("required_fields")
        if isinstance(raw_req, list):
            required = [str(x) for x in raw_req]

    sections: list[str] = [EXTERNAL_FALLBACK_PROMPT_TEXT.strip()]
    sources: list[dict[str, str]] = [
        {
            "block": "base",
            "key": EXTERNAL_FALLBACK_PROMPT_KEY,
            "version": EXTERNAL_FALLBACK_PROMPT_VERSION,
        }
    ]

    client_section = _client_rules_section(client_rules)
    if client_section:
        sections.append(client_section)
        sources.append(
            {
                "block": "client_rules",
                "key": str((client_rules or {}).get("client_rule_key") or "client_rules"),
                "version": str((client_rules or {}).get("client_rule_version") or ""),
            }
        )

    supplier_section = _supplier_profile_section(supplier_extraction_profile)
    if supplier_section:
        sections.append(supplier_section)
        sources.append(
            {
                "block": "supplier_extraction_profile",
                "key": str(
                    (supplier_extraction_profile or {}).get("profile_key")
                    or (supplier_extraction_profile or {}).get("supplier_profile_id")
                    or "supplier_profile"
                ),
                "version": str((supplier_extraction_profile or {}).get("profile_version") or ""),
            }
        )

    runtime = _runtime_section(
        quantity_max=quantity_max,
        strategy=strategy,
        required_fields=required,
    )
    if runtime:
        sections.append(runtime)
        sources.append({"block": "runtime", "key": "runtime_context", "version": "1"})

    sections.append(_OUTPUT_CONTRACT.strip())
    sources.append(
        {
            "block": "output_contract",
            "key": LlmSchemaVersion.EXTERNAL_FALLBACK_V1,
            "version": EXTERNAL_FALLBACK_COMPOSITION_VERSION,
        }
    )

    text = "\n\n".join(sections).strip() + "\n"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "text": text,
        "prompt_key": EXTERNAL_FALLBACK_PROMPT_KEY,
        "prompt_version": EXTERNAL_FALLBACK_PROMPT_VERSION,
        "composition_version": EXTERNAL_FALLBACK_COMPOSITION_VERSION,
        "schema_version": LlmSchemaVersion.EXTERNAL_FALLBACK_V1,
        "sha256": digest,
        "length": len(text),
        "sources": sources,
    }


def build_external_fallback_prompt(
    *,
    client_rules: dict | None = None,
    supplier_extraction_profile: dict | None = None,
    quantity_max: int | None = None,
    strategy: str | None = None,
) -> str:
    """Compose the versioned prompt text (compat wrapper)."""
    return str(
        compose_external_fallback_prompt(
            client_rules=client_rules,
            supplier_extraction_profile=supplier_extraction_profile,
            quantity_max=quantity_max,
            strategy=strategy,
        )["text"]
    )


def build_external_provider_trace_metadata(
    *,
    llm_provider: str | None = None,
    requested_model: str | None = None,
    executed_model: str | None = None,
    adapter_name: str | None = None,
    schema_version: str | None = None,
    prompt_key: str | None = None,
    prompt_version: str | None = None,
    prompt_sha256: str | None = None,
    prompt_length: int | None = None,
    request_image_sha256_raw: str | None = None,
    request_image_sha256_prepared: str | None = None,
    provider_response_sha256: str | None = None,
    attempt_number: int | None = None,
    provider_request_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single builder for external-provider event/result metadata (no secrets)."""
    meta: dict[str, Any] = {
        "provider": (llm_provider or "").strip().lower() or None,
        "requested_model": requested_model,
        "executed_model": executed_model,
        "adapter_name": adapter_name,
        "schema_version": schema_version,
        "prompt_key": prompt_key,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "prompt_length": prompt_length,
        "request_image_sha256_raw": request_image_sha256_raw,
        "request_image_sha256_prepared": request_image_sha256_prepared,
        # Stable alias: raw asset bytes for this call.
        "request_image_sha256": request_image_sha256_raw,
        "provider_response_sha256": provider_response_sha256,
        "attempt_number": attempt_number,
        "provider_request_id": provider_request_id,
    }
    if extra:
        for key, value in extra.items():
            if key not in meta or meta[key] is None:
                meta[key] = value
    return {k: v for k, v in meta.items() if v is not None}


def prompt_composition_public_dict(composed: dict[str, Any]) -> dict[str, Any]:
    """Sanitized composition metadata suitable for snapshots / DTOs (no secrets)."""
    return {
        "base_key": EXTERNAL_FALLBACK_PROMPT_KEY,
        "base_version": EXTERNAL_FALLBACK_PROMPT_VERSION,
        "composition_version": composed.get("composition_version"),
        "schema_version": composed.get("schema_version"),
        "sha256": composed.get("sha256"),
        "length": composed.get("length"),
        "sources": list(composed.get("sources") or []),
    }


def dump_composition_fingerprint(composed: dict[str, Any]) -> str:
    payload = prompt_composition_public_dict(composed)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


__all__ = [
    "EXTERNAL_FALLBACK_COMPOSITION_VERSION",
    "EXTERNAL_FALLBACK_PROMPT_KEY",
    "EXTERNAL_FALLBACK_PROMPT_TEXT",
    "EXTERNAL_FALLBACK_PROMPT_VERSION",
    "build_external_fallback_prompt",
    "build_external_provider_trace_metadata",
    "compose_external_fallback_prompt",
    "dump_composition_fingerprint",
    "prompt_composition_public_dict",
]
