"""
Phase 3 / 5 — **compatibility** mapping for per-job model name on ``LLMRequest.metadata``.

``LLMRequest`` stays provider-neutral at the type level; adapters still read **legacy** keys
(``gemini_model_name``, ``openai_model_name``, ``claude_model_name``, ``deepseek_model_name``).
This module is the **only** place that maps ``(resolved_provider_key, job_model_name)`` onto those
keys so hybrid orchestration does not branch on vendor.

**Intentionally retained:** vendor-specific key names at the adapter boundary until adapters accept
a single neutral field (deferred; would require adapter refactors).
"""

from __future__ import annotations

from typing import Any, Final, Mapping, MutableMapping, Optional

# Canonical map: normalized pipeline provider key → ``LLMRequest.metadata`` key adapters read.
_LEGACY_VENDOR_MODEL_METADATA_KEY: Final[Mapping[str, str]] = {
    "gemini": "gemini_model_name",
    "openai": "openai_model_name",
    "claude": "claude_model_name",
    "deepseek": "deepseek_model_name",
}


def _strip_job_model_name(job_model_name: Optional[str]) -> Optional[str]:
    jm = str(job_model_name).strip() if job_model_name and str(job_model_name).strip() else None
    return jm


def apply_job_model_name_to_llm_request_metadata(
    *,
    resolved_provider_key: str,
    job_model_name: Optional[str],
    metadata: MutableMapping[str, Any],
) -> Optional[str]:
    """
    Compatibility: when ``job_model_name`` is set, write the legacy per-vendor model key on ``metadata``.

    Returns the stripped model string for prompt composition / traceability, or ``None`` when there
    is no job model. For an unknown ``resolved_provider_key`` (not in the registered adapter set
    above), returns the stripped model without mutating ``metadata`` — same behavior as the
    pre–Phase 5 branch layout.
    """
    jm = _strip_job_model_name(job_model_name)
    if not jm:
        return None
    rk = (resolved_provider_key or "").strip().lower()
    meta_key = _LEGACY_VENDOR_MODEL_METADATA_KEY.get(rk)
    if meta_key is not None:
        metadata[meta_key] = jm
    return jm
