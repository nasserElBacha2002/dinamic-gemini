"""Phase 8 — Claude uses the same hybrid base fragment as Gemini (not the OpenAI overlay)."""

from __future__ import annotations

import pytest

from src.llm.prompt_composer.hybrid_profiles import PROMPTS
from src.llm.prompt_composer.hybrid_resolution import resolve_hybrid_entry_for_provider


def test_claude_resolves_same_hybrid_base_as_gemini() -> None:
    entry = PROMPTS.get("global_v21")
    if not isinstance(entry, dict):
        pytest.skip("global_v21 is not a dict-shaped hybrid entry")
    gemini = resolve_hybrid_entry_for_provider(entry, "gemini")
    claude = resolve_hybrid_entry_for_provider(entry, "claude")
    default_branch = resolve_hybrid_entry_for_provider(entry, None)
    assert claude == gemini == default_branch
    if isinstance(entry.get("openai"), str):
        openai = resolve_hybrid_entry_for_provider(entry, "openai")
        assert openai == str(entry["openai"]).rstrip()
