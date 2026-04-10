"""
Hybrid analysis prompt composer — **single source of truth** for hybrid **base** prompt text.

``compose_base`` is the only supported entry point for profile + provider resolution in production
code paths; ``src.llm.prompts.get_hybrid_prompt`` delegates here for backward compatibility.

Enrichments (image IDs, product/label blocks) live in ``prompt_composer.enrichments`` and are
applied only at explicit call sites (e.g. ``hybrid_analysis_prompt``), never inside the composer.
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
    Phase 5+ by explicit per-provider policy — do not assume future vendors inherit OpenAI text.
    """

    def compose_base(self, profile_name: str, provider_key: Optional[str] = None) -> str:
        """
        Return base analysis prompt for the hybrid pipeline only (no traceability / Epic D blocks).

        Unknown ``profile_name`` falls back to ``global_v21`` with the same ``provider_key``,
        matching historical ``get_hybrid_prompt`` semantics.
        """
        raw = PROMPTS.get(profile_name)
        if raw is None:
            return resolve_hybrid_entry_for_provider(PROMPTS["global_v21"], provider_key)
        return resolve_hybrid_entry_for_provider(raw, provider_key)


default_hybrid_composer = HybridPromptComposer()
