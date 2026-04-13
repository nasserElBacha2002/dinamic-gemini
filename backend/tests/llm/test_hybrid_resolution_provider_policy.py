"""Hybrid provider resolution: OpenAI replacement overlay; Claude default + canonical supplement; DeepSeek default."""

from __future__ import annotations

import pytest

from src.llm.prompt_composer.hybrid_profiles import CLAUDE_CONTRACT_MARKER, PROMPTS
from src.llm.prompt_composer.hybrid_resolution import resolve_hybrid_entry_for_provider


def test_claude_resolves_default_plus_canonical_supplement() -> None:
    entry = PROMPTS.get("global_v21")
    if not isinstance(entry, dict):
        pytest.skip("global_v21 is not a dict-shaped hybrid entry")
    gemini = resolve_hybrid_entry_for_provider(entry, "gemini")
    claude = resolve_hybrid_entry_for_provider(entry, "claude")
    default_branch = resolve_hybrid_entry_for_provider(entry, None)
    assert gemini == default_branch
    assert claude != gemini
    assert claude.startswith(gemini)
    assert CLAUDE_CONTRACT_MARKER in claude
    if isinstance(entry.get("openai"), str):
        openai = resolve_hybrid_entry_for_provider(entry, "openai")
        assert openai == str(entry["openai"]).rstrip()


def test_deepseek_resolves_same_hybrid_base_as_gemini() -> None:
    entry = PROMPTS.get("global_v21")
    if not isinstance(entry, dict):
        pytest.skip("global_v21 is not a dict-shaped hybrid entry")
    gemini = resolve_hybrid_entry_for_provider(entry, "gemini")
    deepseek = resolve_hybrid_entry_for_provider(entry, "deepseek")
    assert deepseek == gemini


def test_claude_supplement_also_applies_for_anthropic_and_claude_model_slug() -> None:
    entry = PROMPTS.get("global_v21")
    if not isinstance(entry, dict):
        pytest.skip("global_v21 is not a dict-shaped hybrid entry")
    base = resolve_hybrid_entry_for_provider(entry, "gemini")
    for pk in ("anthropic", "claude-3-5-sonnet-20241022"):
        t = resolve_hybrid_entry_for_provider(entry, pk)
        assert t != base
        assert t.startswith(base)
        assert CLAUDE_CONTRACT_MARKER in t


def test_parity_strips_claude_supplement_for_anthropic_alias() -> None:
    entry = PROMPTS.get("global_v21")
    if not isinstance(entry, dict):
        pytest.skip("global_v21 is not a dict-shaped hybrid entry")
    full = resolve_hybrid_entry_for_provider(entry, "anthropic", prompt_parity_mode=False)
    parity = resolve_hybrid_entry_for_provider(entry, "anthropic", prompt_parity_mode=True)
    assert CLAUDE_CONTRACT_MARKER in full
    assert CLAUDE_CONTRACT_MARKER not in parity
    assert parity == resolve_hybrid_entry_for_provider(entry, "gemini", prompt_parity_mode=False)


def test_openai_parity_mode_matches_default_branch() -> None:
    entry = PROMPTS.get("global_v21")
    if not isinstance(entry, dict):
        pytest.skip("global_v21 is not a dict-shaped hybrid entry")
    default_branch = resolve_hybrid_entry_for_provider(entry, None)
    parity_openai = resolve_hybrid_entry_for_provider(entry, "openai", prompt_parity_mode=True)
    assert parity_openai == default_branch
    if isinstance(entry.get("openai"), str):
        overlay = resolve_hybrid_entry_for_provider(entry, "openai", prompt_parity_mode=False)
        assert overlay == str(entry["openai"]).rstrip()


def test_parity_mode_does_not_change_gemini_deepseek_or_default() -> None:
    entry = PROMPTS.get("global_v21")
    if not isinstance(entry, dict):
        pytest.skip("global_v21 is not a dict-shaped hybrid entry")
    for pk in ("gemini", "deepseek", None):
        a = resolve_hybrid_entry_for_provider(entry, pk, prompt_parity_mode=False)
        b = resolve_hybrid_entry_for_provider(entry, pk, prompt_parity_mode=True)
        assert a == b


def test_parity_mode_strips_claude_supplement() -> None:
    entry = PROMPTS.get("global_v21")
    if not isinstance(entry, dict):
        pytest.skip("global_v21 is not a dict-shaped hybrid entry")
    with_sup = resolve_hybrid_entry_for_provider(entry, "claude", prompt_parity_mode=False)
    parity = resolve_hybrid_entry_for_provider(entry, "claude", prompt_parity_mode=True)
    assert CLAUDE_CONTRACT_MARKER in with_sup
    assert CLAUDE_CONTRACT_MARKER not in parity
    assert parity == resolve_hybrid_entry_for_provider(entry, "gemini", prompt_parity_mode=False)
