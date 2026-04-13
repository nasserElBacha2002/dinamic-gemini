"""
Phase 5 — **official production entrypoint** for hybrid **base** prompt text (no enrichments).

**Which API to use**

* **Pipeline / strategy** (have ``RunContext``): call ``resolve_hybrid_profile_name`` then
  ``compose_hybrid_base(profile, effective_provider_key)`` — same as
  ``pipeline.services.hybrid_analysis_prompt`` does after ``normalize_pipeline_provider_key``.
* **SDK adapters** (empty ``LLMRequest.prompt``, have ``settings``): call only
  ``compose_hybrid_base_from_settings`` — it resolves profile from settings (optional job key) and
  delegates composition; **no enrichments**, **no extra fallbacks** beyond profile + composer.
* **Legacy / unit tests**: ``src.llm.prompts.get_hybrid_prompt`` remains a thin wrapper around
  ``default_hybrid_composer.compose_base``; do not add new production call sites there.

**Internal wiring**

* ``compose_hybrid_base`` is the single production wrapper around the composer instance; prefer it
  over calling ``default_hybrid_composer.compose_base`` directly so resolution stays discoverable.

**Four-step flow** (enrichments are step 4, outside this module)

1. Resolve profile — ``job_prompt_key`` wins; else ``settings.hybrid_prompt`` (default ``global_v21``).
2. Resolve provider key — caller supplies pipeline provider string (e.g. from
   ``normalize_pipeline_provider_key``); adapters pass ``None`` (default fragment) or ``\"openai\"``.
3. Compose base — ``compose_hybrid_base`` → ``HybridPromptComposer.compose_base`` →
   ``resolve_hybrid_entry_for_provider`` only.
4. Apply enrichments — exclusively at explicit call sites (e.g. ``hybrid_analysis_prompt`` for photo
   image IDs). Phase 6 (traceability) will extend this layer, not the composer.

**Provider overlay (temporary, parity-driven)**

The ``default`` vs ``openai`` fragment rule lives in ``hybrid_resolution`` only. Future vendors must
not rely on that heuristic; it will be replaced by explicit policy (see ``hybrid_resolution`` docs).
"""

from __future__ import annotations

from typing import Any, Optional

from src.llm.prompt_composer.composer import default_hybrid_composer


def resolve_hybrid_profile_name(*, job_prompt_key: Optional[Any], settings: Any) -> str:
    """Effective hybrid profile key for a run (job override beats ``settings.hybrid_prompt``)."""
    if job_prompt_key is not None and str(job_prompt_key).strip():
        return str(job_prompt_key).strip()
    return str(getattr(settings, "hybrid_prompt", "global_v21") or "global_v21").strip()


def compose_hybrid_base(
    profile: str,
    pipeline_provider_key: Optional[str],
    *,
    prompt_parity_mode: bool = False,
) -> str:
    """
    Production helper: composed **base** text only (delegates to ``HybridPromptComposer``).

    Do not add enrichments here; do not bypass ``hybrid_resolution``.
    """
    return default_hybrid_composer.compose_base(
        profile, pipeline_provider_key, prompt_parity_mode=prompt_parity_mode
    )


def compose_hybrid_base_from_settings(
    settings: Any,
    *,
    pipeline_provider_key: Optional[str],
    job_prompt_key: Optional[Any] = None,
    prompt_parity_mode: bool = False,
) -> str:
    """
    Adapter fallback when ``LLMRequest.prompt`` is empty.

    **Responsibilities:** (1) resolve profile via ``resolve_hybrid_profile_name``;
    (2) call ``compose_hybrid_base``. **Only** those steps — no enrichments, no adapter-specific
    prompt branches, no registry access outside the composer stack.

    ``prompt_parity_mode`` must match ``LLMRequest.metadata`` / ``RunContext.job_prompt_parity_mode``
    when adapters compose base text for comparison runs.
    """
    profile = resolve_hybrid_profile_name(job_prompt_key=job_prompt_key, settings=settings)
    return compose_hybrid_base(
        profile, pipeline_provider_key, prompt_parity_mode=prompt_parity_mode
    )
