"""
Phase 3 — provider-specific *request metadata* mapping for hybrid global analysis.

Historically each ``LlmGlobalAnalysisExecutor`` read a vendor-specific key on ``LLMRequest.metadata``
(``gemini_model_name``, ``openai_model_name``, etc.). This module centralizes that mapping so
orchestration / strategy code stays free of ``if provider == ...`` branches.

**Deferred:** converging adapters onto a single neutral metadata field (see adapter comments).
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
    Mutate ``metadata`` with the per-adapter model key when ``job_model_name`` is set.

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
