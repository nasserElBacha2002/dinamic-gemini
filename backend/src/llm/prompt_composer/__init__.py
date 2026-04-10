"""
Hybrid prompt composition (Phase 4–5).

**Base text (production):** ``hybrid_assembly`` only. ``HybridPromptComposer.compose_base`` is internal
to that stack plus ``get_hybrid_prompt`` (legacy/tests).

**Compatibility:** ``src.llm.prompts.get_hybrid_prompt`` remains a thin test/legacy delegate.

**Enrichments:** ``prompt_composer.enrichments`` only; pipeline applies them in
``pipeline.services.hybrid_analysis_prompt``.
"""

from __future__ import annotations

from src.llm.prompt_composer.composer import HybridPromptComposer, default_hybrid_composer

__all__ = ["HybridPromptComposer", "default_hybrid_composer"]
