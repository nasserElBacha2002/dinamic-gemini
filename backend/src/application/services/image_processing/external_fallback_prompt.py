"""Phase 5 — versioned prompt for single-image external label analysis."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.llm.schema_versions import LlmSchemaVersion

EXTERNAL_FALLBACK_PROMPT_KEY = "external_fallback_single_label"
EXTERNAL_FALLBACK_PROMPT_VERSION = "1.0.0"
EXTERNAL_FALLBACK_COMPOSITION_VERSION = "2"

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


class SupplierPromptConfigError(ValueError):
    """Configuration error before any external LLM call."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ResolvedSupplierPrompt:
    """Textual supplier prompt from supplier_prompt_configs (not extraction profile JSON)."""

    supplier_id: str
    extraction_profile_id: str | None
    prompt_id: str
    prompt_key: str
    prompt_version: str
    content: str
    source_level: str
    is_active: bool
    content_sha256: str
    resolved_at: str

    def public_snapshot(self, *, include_content: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "supplier_id": self.supplier_id,
            "extraction_profile_id": self.extraction_profile_id,
            "prompt_id": self.prompt_id,
            "prompt_key": self.prompt_key,
            "prompt_version": self.prompt_version,
            "content_sha256": self.content_sha256,
            "source_level": self.source_level,
            "is_active": self.is_active,
            "required": True,
            "resolved_at": self.resolved_at,
            "content_length": len(self.content),
        }
        if include_content:
            out["content"] = self.content
        return out


@dataclass(frozen=True)
class EffectiveExternalFallbackPrompt:
    """Single composed prompt for one fallback execution (hash == bytes sent to LLM)."""

    text: str
    base_prompt_key: str
    base_prompt_version: str
    supplier_prompt_id: str | None
    supplier_prompt_key: str | None
    supplier_prompt_version: str | None
    supplier_prompt_sha256: str | None
    supplier_prompt_loaded: bool
    supplier_prompt_required: bool
    composition_version: str
    schema_version: str
    sha256: str
    length: int
    sources: tuple[dict[str, str], ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "base_prompt_key": self.base_prompt_key,
            "base_prompt_version": self.base_prompt_version,
            "supplier_prompt_id": self.supplier_prompt_id,
            "supplier_prompt_key": self.supplier_prompt_key,
            "supplier_prompt_version": self.supplier_prompt_version,
            "supplier_prompt_sha256": self.supplier_prompt_sha256,
            "supplier_prompt_loaded": self.supplier_prompt_loaded,
            "supplier_prompt_required": self.supplier_prompt_required,
            "composition_version": self.composition_version,
            "schema_version": self.schema_version,
            "sha256": self.sha256,
            "length": self.length,
            "sources": list(self.sources),
        }


def build_resolved_supplier_prompt(
    *,
    supplier_id: str,
    prompt_id: str,
    prompt_version: int | str,
    content: str,
    extraction_profile_id: str | None = None,
    source_level: str = "aisle.client_supplier",
    is_active: bool = True,
    prompt_key: str = "supplier_prompt_config",
    resolved_at: datetime | None = None,
) -> ResolvedSupplierPrompt:
    text = (content or "").strip()
    if not text:
        raise SupplierPromptConfigError(
            "SUPPLIER_PROMPT_EMPTY",
            "supplier prompt instructions_text is empty",
        )
    if not is_active:
        raise SupplierPromptConfigError(
            "SUPPLIER_PROMPT_INACTIVE",
            "supplier prompt is inactive",
        )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    at = resolved_at or datetime.now(timezone.utc)
    return ResolvedSupplierPrompt(
        supplier_id=str(supplier_id).strip(),
        extraction_profile_id=(
            str(extraction_profile_id).strip() if extraction_profile_id else None
        ),
        prompt_id=str(prompt_id).strip(),
        prompt_key=prompt_key,
        prompt_version=str(prompt_version),
        content=text,
        source_level=source_level,
        is_active=True,
        content_sha256=digest,
        resolved_at=at.isoformat(),
    )


def resolved_supplier_prompt_from_snapshot(
    raw: dict[str, Any] | None,
    *,
    required: bool,
) -> ResolvedSupplierPrompt | None:
    """Rebuild typed supplier prompt from job identification snapshot."""
    if not isinstance(raw, dict) or not raw:
        if required:
            raise SupplierPromptConfigError(
                "SUPPLIER_PROMPT_REQUIRED",
                "supplier associated but supplier_prompt snapshot is missing",
            )
        return None
    content = raw.get("content")
    if not isinstance(content, str) or not content.strip():
        if required:
            raise SupplierPromptConfigError(
                "SUPPLIER_PROMPT_EMPTY",
                "supplier_prompt snapshot has empty content",
            )
        return None
    prompt_id = str(raw.get("prompt_id") or "").strip()
    supplier_id = str(raw.get("supplier_id") or "").strip()
    if not prompt_id or not supplier_id:
        raise SupplierPromptConfigError(
            "SUPPLIER_PROMPT_SNAPSHOT_MISMATCH",
            "supplier_prompt snapshot missing prompt_id or supplier_id",
        )
    digest = str(raw.get("content_sha256") or "").strip()
    computed = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
    if digest and digest != computed:
        raise SupplierPromptConfigError(
            "SUPPLIER_PROMPT_SNAPSHOT_MISMATCH",
            "supplier_prompt snapshot content_sha256 does not match content",
        )
    return ResolvedSupplierPrompt(
        supplier_id=supplier_id,
        extraction_profile_id=(
            str(raw["extraction_profile_id"]).strip()
            if raw.get("extraction_profile_id")
            else None
        ),
        prompt_id=prompt_id,
        prompt_key=str(raw.get("prompt_key") or "supplier_prompt_config"),
        prompt_version=str(raw.get("prompt_version") or ""),
        content=content.strip(),
        source_level=str(raw.get("source_level") or "snapshot"),
        is_active=bool(raw.get("is_active", True)),
        content_sha256=digest or computed,
        resolved_at=str(raw.get("resolved_at") or datetime.now(timezone.utc).isoformat()),
    )


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


def _supplier_custom_instructions_section(supplier_prompt: ResolvedSupplierPrompt) -> str:
    return (
        "[SUPPLIER CUSTOM INSTRUCTIONS]\n"
        f"- prompt_id: {supplier_prompt.prompt_id}\n"
        f"- prompt_key: {supplier_prompt.prompt_key}\n"
        f"- prompt_version: {supplier_prompt.prompt_version}\n"
        f"- content_sha256: {supplier_prompt.content_sha256}\n"
        f"- source: {supplier_prompt.source_level}\n"
        f"{supplier_prompt.content.strip()}"
    )


def _supplier_profile_section(supplier_extraction_profile: dict[str, Any] | None) -> str | None:
    """Render structured extraction-profile rules (not free-text supplier prompt)."""
    if not isinstance(supplier_extraction_profile, dict) or not supplier_extraction_profile:
        return None
    lines = ["[SUPPLIER EXTRACTION PROFILE]"]
    for key in (
        "supplier_profile_id",
        "supplier_profile_key",
        "supplier_profile_version",
        "profile_key",
        "profile_version",
        "supplier_id",
        "source",
    ):
        val = supplier_extraction_profile.get(key)
        if val is not None and str(val).strip():
            lines.append(f"- {key}: {str(val).strip()[:120]}")

    cfg = supplier_extraction_profile.get("configuration")
    if not isinstance(cfg, dict):
        cfg = {}

    code_rules = None
    validation_rules = cfg.get("validation_rules")
    if isinstance(validation_rules, dict) and isinstance(validation_rules.get("code"), dict):
        code_rules = validation_rules.get("code")
    elif isinstance(cfg.get("code_validation"), dict):
        code_rules = cfg.get("code_validation")
    if isinstance(code_rules, dict):
        for rk in (
            "exact_length",
            "min_length",
            "max_length",
            "charset",
            "pattern",
            "required",
        ):
            if code_rules.get(rk) is not None:
                lines.append(f"- code.{rk}: {code_rules.get(rk)}")

    qty_rules = cfg.get("quantity_rules")
    if not isinstance(qty_rules, dict):
        qty_rules = supplier_extraction_profile.get("quantity_rules")
    if isinstance(qty_rules, dict):
        for rk in ("required", "minimum", "maximum", "min", "max"):
            if qty_rules.get(rk) is not None:
                lines.append(f"- quantity.{rk}: {qty_rules.get(rk)}")

    label_rules = cfg.get("label_detection_rules")
    if isinstance(label_rules, dict):
        anchors = label_rules.get("primary_anchors") or label_rules.get("anchors")
        if isinstance(anchors, list) and anchors:
            safe = [str(a)[:40] for a in anchors[:8]]
            lines.append("- label anchors: " + ", ".join(safe))

    required = supplier_extraction_profile.get("required_fields") or cfg.get("required_fields")
    if isinstance(required, list) and required:
        lines.append("- required_fields: " + ", ".join(str(x) for x in required[:12]))

    visual_notes = supplier_extraction_profile.get("visual_notes")
    if isinstance(visual_notes, str) and visual_notes.strip():
        lines.append("- visual_notes:\n" + visual_notes.strip())

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
    supplier_prompt: ResolvedSupplierPrompt | None = None,
    supplier_prompt_required: bool = False,
    quantity_max: int | None = None,
    strategy: str | None = None,
) -> EffectiveExternalFallbackPrompt:
    """Compose the effective fallback prompt once (deterministic sections + hash)."""
    if supplier_prompt_required and supplier_prompt is None:
        raise SupplierPromptConfigError(
            "SUPPLIER_PROMPT_REQUIRED",
            "supplier_prompt_required=true but supplier_prompt is None",
        )
    if supplier_prompt is not None and not supplier_prompt.content.strip():
        raise SupplierPromptConfigError(
            "SUPPLIER_PROMPT_EMPTY",
            "supplier_prompt content is empty",
        )

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

    if supplier_prompt is not None:
        sections.append(_supplier_custom_instructions_section(supplier_prompt))
        sources.append(
            {
                "block": "supplier_custom_instructions",
                "key": supplier_prompt.prompt_key,
                "version": supplier_prompt.prompt_version,
                "prompt_id": supplier_prompt.prompt_id,
                "content_sha256": supplier_prompt.content_sha256,
            }
        )

    supplier_section = _supplier_profile_section(supplier_extraction_profile)
    if supplier_section:
        sections.append(supplier_section)
        sources.append(
            {
                "block": "supplier_extraction_profile",
                "key": str(
                    (supplier_extraction_profile or {}).get("supplier_profile_key")
                    or (supplier_extraction_profile or {}).get("profile_key")
                    or (supplier_extraction_profile or {}).get("supplier_profile_id")
                    or "supplier_profile"
                ),
                "version": str(
                    (supplier_extraction_profile or {}).get("supplier_profile_version")
                    or (supplier_extraction_profile or {}).get("profile_version")
                    or ""
                ),
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
    return EffectiveExternalFallbackPrompt(
        text=text,
        base_prompt_key=EXTERNAL_FALLBACK_PROMPT_KEY,
        base_prompt_version=EXTERNAL_FALLBACK_PROMPT_VERSION,
        supplier_prompt_id=supplier_prompt.prompt_id if supplier_prompt else None,
        supplier_prompt_key=supplier_prompt.prompt_key if supplier_prompt else None,
        supplier_prompt_version=supplier_prompt.prompt_version if supplier_prompt else None,
        supplier_prompt_sha256=supplier_prompt.content_sha256 if supplier_prompt else None,
        supplier_prompt_loaded=supplier_prompt is not None,
        supplier_prompt_required=bool(supplier_prompt_required),
        composition_version=EXTERNAL_FALLBACK_COMPOSITION_VERSION,
        schema_version=LlmSchemaVersion.EXTERNAL_FALLBACK_V1,
        sha256=digest,
        length=len(text),
        sources=tuple(sources),
    )


def build_external_fallback_prompt(
    *,
    client_rules: dict | None = None,
    supplier_extraction_profile: dict | None = None,
    supplier_prompt: ResolvedSupplierPrompt | None = None,
    supplier_prompt_required: bool = False,
    quantity_max: int | None = None,
    strategy: str | None = None,
) -> str:
    """Compose the versioned prompt text (compat wrapper)."""
    return compose_external_fallback_prompt(
        client_rules=client_rules,
        supplier_extraction_profile=supplier_extraction_profile,
        supplier_prompt=supplier_prompt,
        supplier_prompt_required=supplier_prompt_required,
        quantity_max=quantity_max,
        strategy=strategy,
    ).text


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


def prompt_composition_public_dict(
    composed: EffectiveExternalFallbackPrompt | dict[str, Any],
) -> dict[str, Any]:
    """Sanitized composition metadata suitable for snapshots / DTOs (no full prompt text)."""
    if isinstance(composed, EffectiveExternalFallbackPrompt):
        return {
            "base_key": composed.base_prompt_key,
            "base_version": composed.base_prompt_version,
            "composition_version": composed.composition_version,
            "schema_version": composed.schema_version,
            "sha256": composed.sha256,
            "length": composed.length,
            "supplier_prompt_id": composed.supplier_prompt_id,
            "supplier_prompt_key": composed.supplier_prompt_key,
            "supplier_prompt_version": composed.supplier_prompt_version,
            "supplier_prompt_sha256": composed.supplier_prompt_sha256,
            "supplier_prompt_loaded": composed.supplier_prompt_loaded,
            "supplier_prompt_required": composed.supplier_prompt_required,
            "sources": list(composed.sources),
        }
    return {
        "base_key": EXTERNAL_FALLBACK_PROMPT_KEY,
        "base_version": EXTERNAL_FALLBACK_PROMPT_VERSION,
        "composition_version": composed.get("composition_version"),
        "schema_version": composed.get("schema_version"),
        "sha256": composed.get("sha256"),
        "length": composed.get("length"),
        "sources": list(composed.get("sources") or []),
    }


def dump_composition_fingerprint(
    composed: EffectiveExternalFallbackPrompt | dict[str, Any],
) -> str:
    payload = prompt_composition_public_dict(composed)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


__all__ = [
    "EXTERNAL_FALLBACK_COMPOSITION_VERSION",
    "EXTERNAL_FALLBACK_PROMPT_KEY",
    "EXTERNAL_FALLBACK_PROMPT_TEXT",
    "EXTERNAL_FALLBACK_PROMPT_VERSION",
    "EffectiveExternalFallbackPrompt",
    "ResolvedSupplierPrompt",
    "SupplierPromptConfigError",
    "build_external_fallback_prompt",
    "build_external_provider_trace_metadata",
    "build_resolved_supplier_prompt",
    "compose_external_fallback_prompt",
    "dump_composition_fingerprint",
    "prompt_composition_public_dict",
    "resolved_supplier_prompt_from_snapshot",
]
