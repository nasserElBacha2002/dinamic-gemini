"""
Phase 3 — **compatibility** mapping for per-job model name on ``LLMRequest.metadata``.

``LLMRequest`` is otherwise provider-neutral; adapters still expect **vendor-specific** keys
(``gemini_model_name``, ``openai_model_name``, ``claude_model_name``, ``deepseek_model_name``).
This module is the single place that maps ``(resolved_provider_key, job_model_name)`` onto those
keys so hybrid orchestration does not branch on vendor.

**Intentionally deferred:** one neutral metadata field for all adapters + adapter refactors.
Until then, request metadata is **not** fully provider-neutral at the ``LLMRequest`` boundary.
"""

from __future__ import annotations

from typing import Any, MutableMapping, Optional


def apply_job_model_name_to_llm_request_metadata(
    *,
    resolved_provider_key: str,
    job_model_name: Optional[str],
    metadata: MutableMapping[str, Any],
) -> Optional[str]:
    """
    Compatibility: mutate ``metadata`` with the legacy per-vendor model key when ``job_model_name`` is set.

    Returns the stripped model string for prompt composition / traceability, or ``None``.
    """
    jm = str(job_model_name).strip() if job_model_name and str(job_model_name).strip() else None
    if not jm:
        return None
    rk = (resolved_provider_key or "").strip().lower()
    if rk == "gemini":
        metadata["gemini_model_name"] = jm
    elif rk == "openai":
        metadata["openai_model_name"] = jm
    elif rk == "claude":
        metadata["claude_model_name"] = jm
    elif rk == "deepseek":
        metadata["deepseek_model_name"] = jm
    return jm
