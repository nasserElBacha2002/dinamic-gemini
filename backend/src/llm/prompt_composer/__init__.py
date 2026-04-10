"""
Phase 4 — hybrid prompt composition (single source of truth for base text + enrichments).

``HybridPromptComposer`` resolves profile + provider policy into the same strings as the
pre–Phase 4 ``get_hybrid_prompt`` API. Public code may import from ``src.llm.prompts`` for
backward compatibility or use ``default_hybrid_composer`` directly.
"""

from __future__ import annotations

from src.llm.prompt_composer.composer import HybridPromptComposer, default_hybrid_composer

__all__ = ["HybridPromptComposer", "default_hybrid_composer"]
