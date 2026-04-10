"""
Hybrid analysis prompt composer — profile selection + provider overlay (Phase 4).

Produces the same base prompt text as the historical ``get_hybrid_prompt`` implementation.
Enrichments (image IDs, product/label blocks) are applied via ``prompt_composer.enrichments``.
"""

from __future__ import annotations

from typing import Optional

from src.llm.prompt_composer.hybrid_profiles import PROMPTS
from src.llm.prompt_composer.hybrid_resolution import resolve_hybrid_entry_for_provider


class HybridPromptComposer:
    """Composes hybrid global-analysis base prompt text from profile + pipeline provider key."""

    def compose_base(self, profile_name: str, provider_key: Optional[str] = None) -> str:
        """
        Return base analysis prompt for the hybrid pipeline (no Epic D / traceability appenders).

        Unknown profiles fall back to ``global_v21`` resolution semantics (unchanged from legacy).
        """
        raw = PROMPTS.get(profile_name)
        if raw is None:
            return resolve_hybrid_entry_for_provider(PROMPTS["global_v21"], provider_key)
        return resolve_hybrid_entry_for_provider(raw, provider_key)


default_hybrid_composer = HybridPromptComposer()
