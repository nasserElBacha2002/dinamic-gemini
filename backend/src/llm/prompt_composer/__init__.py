"""
Phase 4 — hybrid prompt composition.

**Base text:** ``HybridPromptComposer.compose_base`` / ``default_hybrid_composer`` is the single
source of truth. ``src.llm.prompts.get_hybrid_prompt`` is a one-line compatibility wrapper.

**Enrichments:** ``prompt_composer.enrichments`` only; never applied inside the composer.
"""

from __future__ import annotations

from src.llm.prompt_composer.composer import HybridPromptComposer, default_hybrid_composer

__all__ = ["HybridPromptComposer", "default_hybrid_composer"]
