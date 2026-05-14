"""
``HybridPromptComposer`` — **internal** registry + overlay engine for hybrid **base** text.

* **Production** should call ``hybrid_assembly.compose_hybrid_base`` / ``compose_hybrid_base_from_settings``
  rather than ``default_hybrid_composer.compose_base`` directly, so entrypoints stay uniform.
* This class is still the only place that reads ``PROMPTS`` and calls ``resolve_hybrid_entry_for_provider``.
* ``src.llm.prompts.get_hybrid_prompt`` delegates to ``compose_base`` for **tests and legacy** only.

Enrichments (image IDs, product/label) live in ``enrichments`` and run only at explicit call sites
(e.g. ``pipeline.services.hybrid_analysis_prompt``). Phase 6 traceability will attach metadata alongside
that layer, not inside ``compose_base``.

See ``hybrid_resolution`` for per-provider rules (OpenAI replacement, Claude supplement, default-only).
"""

from __future__ import annotations

from src.llm.prompt_composer.hybrid_profiles import PROMPTS
from src.llm.prompt_composer.hybrid_resolution import resolve_hybrid_entry_for_provider


class HybridPromptComposer:
    """
    Composes hybrid global-analysis **base** prompt text from profile + pipeline provider key.

    Provider rules are implemented in ``resolve_hybrid_entry_for_provider``: ``openai`` replaces
    with the OpenAI fragment; ``claude`` appends the canonical JSON entity contract to ``default``;
    other keys use ``default`` only (see module doc there).
    """

    def compose_base(
        self,
        profile_name: str,
        provider_key: str | None = None,
        *,
        prompt_parity_mode: bool = False,
    ) -> str:
        """
        Return base analysis prompt for the hybrid pipeline only (no traceability / Epic D blocks).

        Unknown or blank ``profile_name`` (including accidental whitespace) uses the **global_v22**
        registry entry so the pipeline never silently downgrades to ``global_v21`` bodies.
        """
        key = (profile_name or "").strip()
        raw = PROMPTS.get(key) if key else None
        if raw is None:
            raw = PROMPTS.get("global_v22") or PROMPTS["global_v21"]
        return resolve_hybrid_entry_for_provider(
            raw, provider_key, prompt_parity_mode=prompt_parity_mode
        )


default_hybrid_composer = HybridPromptComposer()
