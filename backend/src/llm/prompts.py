"""
Legacy façade: **do not use for new production code.**

Prefer ``src.llm.prompt_composer.hybrid_assembly`` for base prompt construction.

Exports here exist for older tests and scripts only:

* ``get_hybrid_prompt`` — thin delegate to ``HybridPromptComposer.compose_base`` (parity checks).
* ``GLOBAL_ENTITY_ANALYSIS_PROMPT_V21`` — stable constant for assertions (not a construction API).
* Enrichment helpers — re-exported for tests; production pipeline imports ``prompt_composer.enrichments``
  directly.

The prompt **registry** (``PROMPTS`` / ``HYBRID_PROMPTS``) is **not** re-exported — import
``hybrid_profiles`` / ``hybrid_resolution`` in tests if you truly need raw registry access.
"""

from __future__ import annotations

from src.llm.prompt_composer.composer import default_hybrid_composer
from src.llm.prompt_composer.enrichments import (
    enrich_prompt_with_image_ids,
    enrich_prompt_with_product_label_association,
)
from src.llm.prompt_composer.hybrid_profiles import GLOBAL_ENTITY_ANALYSIS_PROMPT_V21

__all__ = [
    "GLOBAL_ENTITY_ANALYSIS_PROMPT_V21",
    "enrich_prompt_with_image_ids",
    "enrich_prompt_with_product_label_association",
    "get_hybrid_prompt",
]


def get_hybrid_prompt(
    profile_name: str = "global_v21",
    provider_key: str | None = None,
) -> str:
    """Legacy/tests only — delegates to ``default_hybrid_composer.compose_base``."""
    return default_hybrid_composer.compose_base(profile_name, provider_key)
