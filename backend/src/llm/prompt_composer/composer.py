"""
``HybridPromptComposer`` — **internal** registry + overlay engine for hybrid **base** text.

* **Production** should call ``hybrid_assembly.compose_hybrid_base`` / ``compose_hybrid_base_from_settings``
  rather than ``default_hybrid_composer.compose_base`` directly, so entrypoints stay uniform.
* This class is still the only place that reads ``PROMPTS`` and calls ``resolve_hybrid_entry_for_provider``.
* ``src.llm.prompts.get_hybrid_prompt`` delegates to ``compose_base`` for **tests and legacy** only.

Enrichments (image IDs, product/label) live in ``enrichments`` and run only at explicit call sites
(e.g. ``pipeline.services.hybrid_analysis_prompt``). Phase 6 traceability will attach metadata alongside
that layer, not inside ``compose_base``.

The ``default`` vs ``openai`` overlay is parity-only; see ``hybrid_resolution`` — future providers need
an explicit map, not this heuristic.
"""

from __future__ import annotations

from typing import Optional

from src.llm.prompt_composer.hybrid_profiles import PROMPTS
from src.llm.prompt_composer.hybrid_resolution import resolve_hybrid_entry_for_provider


class HybridPromptComposer:
    """
    Composes hybrid global-analysis **base** prompt text from profile + pipeline provider key.

    Provider overlay rules are implemented in ``resolve_hybrid_entry_for_provider`` (Phase 4
    parity model: only ``openai`` selects the ``openai`` fragment; all other keys use ``default``).
    That model is intentional for parity with pre-composer behavior and will be superseded in
    Phase 6+ by explicit per-provider policy — do not assume future vendors inherit OpenAI text.
    """

    def compose_base(
        self,
        profile_name: str,
        provider_key: Optional[str] = None,
        *,
        prompt_parity_mode: bool = False,
    ) -> str:
        """
        Return base analysis prompt for the hybrid pipeline only (no traceability / Epic D blocks).

        Unknown ``profile_name`` falls back to ``global_v21`` with the same ``provider_key``,
        matching historical ``get_hybrid_prompt`` semantics.
        """
        raw = PROMPTS.get(profile_name)
        if raw is None:
            return resolve_hybrid_entry_for_provider(
                PROMPTS["global_v21"], provider_key, prompt_parity_mode=prompt_parity_mode
            )
        return resolve_hybrid_entry_for_provider(
            raw, provider_key, prompt_parity_mode=prompt_parity_mode
        )


default_hybrid_composer = HybridPromptComposer()
