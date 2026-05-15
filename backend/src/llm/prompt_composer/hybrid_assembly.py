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

1. Resolve profile — product policy: **always** ``DEFAULT_HYBRID_PROMPT_PROFILE`` (``global_v22``).
   ``compose_hybrid_base`` defaults to ``restrict_to_default_aisle_profile=True`` so the composed
   registry key cannot drift to ``global_v21`` even if a stale caller passes a legacy profile string.
   ``job_prompt_key`` / ``settings.hybrid_prompt`` are still recorded in traceability metadata as hints.
2. Resolve provider key — caller supplies pipeline provider string (e.g. from
   ``normalize_pipeline_provider_key``); adapters may pass ``\"claude\"`` (default + canonical JSON
   supplement), ``\"openai\"`` (OpenAI replacement fragment), or ``None`` / other keys (default only).
3. Compose base — ``compose_hybrid_base`` → ``HybridPromptComposer.compose_base`` →
   ``resolve_hybrid_entry_for_provider`` only.
4. Apply enrichments — exclusively at explicit call sites (e.g. ``hybrid_analysis_prompt`` for photo
   image IDs). Phase 6 (traceability) will extend this layer, not the composer.

**Provider overlay (temporary, parity-driven)**

The ``default`` vs ``openai`` fragment rule lives in ``hybrid_resolution`` only. Future vendors must
not rely on that heuristic; it will be replaced by explicit policy (see ``hybrid_resolution`` docs).
"""

from __future__ import annotations

from typing import Any, Final

from src.llm.prompt_composer.composer import default_hybrid_composer

# Single label-first hybrid profile used for all composed aisle-analysis runs (same JSON contract).
DEFAULT_HYBRID_PROMPT_PROFILE: Final[str] = "global_v22"


def resolve_hybrid_profile_name(*, job_prompt_key: Any | None, settings: Any) -> str:
    """Always use the label-first v2.2 profile; ``job_prompt_key`` / ``settings`` do not switch bodies."""
    del job_prompt_key, settings
    return DEFAULT_HYBRID_PROMPT_PROFILE


def compose_hybrid_base(
    profile: str,
    pipeline_provider_key: str | None,
    *,
    prompt_parity_mode: bool = False,
    restrict_to_default_aisle_profile: bool = True,
) -> str:
    """
    Production helper: composed **base** text only (delegates to ``HybridPromptComposer``).

    Do not add enrichments here; do not bypass ``hybrid_resolution``.

    When ``restrict_to_default_aisle_profile`` is True (default), the registry key is always
    ``DEFAULT_HYBRID_PROMPT_PROFILE`` so stale workers or accidental ``global_v21`` arguments cannot
    ship logistics-first bodies to aisle analysis. Admin prompt inspection and regression tests that
    need v21/v21_b bodies pass ``restrict_to_default_aisle_profile=False``.
    """
    if restrict_to_default_aisle_profile:
        key = DEFAULT_HYBRID_PROMPT_PROFILE
    else:
        key = (profile or "").strip()
    return default_hybrid_composer.compose_base(
        key, pipeline_provider_key, prompt_parity_mode=prompt_parity_mode
    )


def compose_hybrid_base_from_settings(
    settings: Any,
    *,
    pipeline_provider_key: str | None,
    job_prompt_key: Any | None = None,
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
        profile,
        pipeline_provider_key,
        prompt_parity_mode=prompt_parity_mode,
        restrict_to_default_aisle_profile=True,
    )
