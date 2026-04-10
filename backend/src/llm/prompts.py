"""Backward-compatible re-exports for hybrid prompts. Core logic: ``prompt_composer`` only."""

from __future__ import annotations

from typing import Optional

from src.llm.prompt_composer.composer import default_hybrid_composer
from src.llm.prompt_composer.enrichments import (
    enrich_prompt_with_image_ids,
    enrich_prompt_with_product_label_association,
)
from src.llm.prompt_composer.hybrid_profiles import GLOBAL_ENTITY_ANALYSIS_PROMPT_V21, PROMPTS
from src.llm.prompt_composer.hybrid_resolution import HYBRID_PROMPTS, registered_hybrid_prompt_keys

__all__ = [
    "GLOBAL_ENTITY_ANALYSIS_PROMPT_V21",
    "HYBRID_PROMPTS",
    "PROMPTS",
    "enrich_prompt_with_image_ids",
    "enrich_prompt_with_product_label_association",
    "get_hybrid_prompt",
    "registered_hybrid_prompt_keys",
]


def get_hybrid_prompt(
    profile_name: str = "global_v21",
    provider_key: Optional[str] = None,
) -> str:
    """Delegate to ``default_hybrid_composer.compose_base`` (base text only; no enrichments)."""
    return default_hybrid_composer.compose_base(profile_name, provider_key)
