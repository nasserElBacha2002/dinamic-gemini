"""
Phase 6 — prompt composition traceability (JSON-serializable, audit-friendly metadata).

Attached to ``LLMRequest.metadata`` and job ``run_metadata`` without changing prompt text.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

# Stable key on ``LLMRequest.metadata`` and job-level run_metadata (optional block).
LLM_METADATA_KEY_PROMPT_COMPOSITION = "prompt_composition"

PROMPT_COMPOSITION_SCHEMA_VERSION = "prompt_composition_v1"


def sha256_utf8(text: str) -> str:
    """SHA-256 hex digest of UTF-8 encoded text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class PromptCompositionMetadata:
    """Structured record of how the hybrid analysis prompt was assembled."""

    schema_version: str
    profile_name: str
    pipeline_provider_key: str
    resolved_llm_provider_key: str
    model_name: Optional[str]
    job_prompt_key: Optional[str]
    settings_hybrid_prompt_key: Optional[str]
    base_prompt_text: str
    final_prompt_text: str
    enrichments_applied: List[str]
    composition_steps: List[Dict[str, Any]]
    prompt_hash: str
    base_prompt_hash: str
    timestamp: str

    def to_json_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_prompt_composition_dict(
    *,
    profile_name: str,
    pipeline_provider_key: str,
    base_prompt_text: str,
    final_prompt_text: str,
    enrichments_applied: Sequence[str],
    composition_steps: Sequence[Dict[str, Any]],
    job_prompt_key: Optional[str],
    settings_hybrid_prompt_key: Optional[str],
    resolved_llm_provider_key: str = "",
    model_name: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a JSON-friendly composition record (hashes computed from prompt strings)."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    meta = PromptCompositionMetadata(
        schema_version=PROMPT_COMPOSITION_SCHEMA_VERSION,
        profile_name=profile_name,
        pipeline_provider_key=pipeline_provider_key,
        resolved_llm_provider_key=(resolved_llm_provider_key or "").strip().lower(),
        model_name=(str(model_name).strip() if model_name and str(model_name).strip() else None),
        job_prompt_key=(str(job_prompt_key).strip() if job_prompt_key and str(job_prompt_key).strip() else None),
        settings_hybrid_prompt_key=(
            str(settings_hybrid_prompt_key).strip()
            if settings_hybrid_prompt_key and str(settings_hybrid_prompt_key).strip()
            else None
        ),
        base_prompt_text=base_prompt_text,
        final_prompt_text=final_prompt_text,
        enrichments_applied=list(enrichments_applied),
        composition_steps=list(composition_steps),
        prompt_hash=sha256_utf8(final_prompt_text),
        base_prompt_hash=sha256_utf8(base_prompt_text),
        timestamp=ts,
    )
    return meta.to_json_dict()


def validate_prompt_composition_dict(meta: Mapping[str, Any]) -> List[str]:
    """
    Return human-readable validation errors; empty list means invariants hold.

    Checks SHA-256 consistency and simple enrichment/base/final alignment.
    """
    errors: List[str] = []
    final = meta.get("final_prompt_text")
    if not isinstance(final, str):
        errors.append("final_prompt_text must be a string")
        return errors
    want_ph = meta.get("prompt_hash")
    if isinstance(want_ph, str) and want_ph:
        if sha256_utf8(final) != want_ph:
            errors.append("prompt_hash does not match final_prompt_text")
    base = meta.get("base_prompt_text")
    if isinstance(base, str):
        want_bh = meta.get("base_prompt_hash")
        if isinstance(want_bh, str) and want_bh:
            if sha256_utf8(base) != want_bh:
                errors.append("base_prompt_hash does not match base_prompt_text")
    enrich = meta.get("enrichments_applied")
    if isinstance(enrich, list) and len(enrich) == 0:
        if isinstance(base, str) and final != base:
            errors.append("enrichments_applied is empty but base_prompt_text != final_prompt_text")
    return errors


def apply_execution_layer_to_composition(
    composition: Dict[str, Any],
    *,
    resolved_llm_provider_key: str,
    model_name: Optional[str],
) -> Dict[str, Any]:
    """Copy composition dict and fill provider/model fields from the execution layer."""
    out = dict(composition)
    out["resolved_llm_provider_key"] = (resolved_llm_provider_key or "").strip().lower()
    out["model_name"] = (str(model_name).strip() if model_name and str(model_name).strip() else None)
    errs = validate_prompt_composition_dict(out)
    for msg in errs:
        logger.warning("prompt_composition validation: %s", msg)
    return out
