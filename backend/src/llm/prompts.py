"""
Unified prompts module — compatibility facade over the Phase 4 prompt composer.

* Registry content lives in ``prompt_composer.hybrid_profiles``.
* Base text resolution: ``HybridPromptComposer.compose_base`` (via ``get_hybrid_prompt``).
* Enrichments: ``prompt_composer.enrichments`` (re-exported here for existing imports).

The pipeline and adapters should prefer ``get_hybrid_prompt`` or ``default_hybrid_composer``; both
delegate to the same composition path.
"""

from __future__ import annotations

from typing import Optional

from src.llm.prompt_composer.composer import default_hybrid_composer
from src.llm.prompt_composer.enrichments import (
    enrich_prompt_with_image_ids,
    enrich_prompt_with_product_label_association,
)
from src.llm.prompt_composer.hybrid_profiles import (
    GLOBAL_ENTITY_ANALYSIS_PROMPT_V21,
    PROMPTS,
)
from src.llm.prompt_composer.hybrid_resolution import (
    HYBRID_PROMPTS,
    registered_hybrid_prompt_keys,
)

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
    """Return the base analysis prompt for the hybrid pipeline (no Epic D enrichment).

    Delegates to ``default_hybrid_composer`` — single source of truth for base text.

    Does not append product/label association. Call ``enrich_prompt_with_product_label_association``
    at the request-building layer where Epic D behavior is intended.
    """
    return default_hybrid_composer.compose_base(profile_name, provider_key)
