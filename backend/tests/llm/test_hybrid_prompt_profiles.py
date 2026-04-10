"""Hybrid prompt profiles (Prompt A vs Prompt B)."""

from __future__ import annotations

from src.llm.prompts import get_hybrid_prompt, registered_hybrid_prompt_keys


def test_global_v21_b_is_registered() -> None:
    assert "global_v21_b" in registered_hybrid_prompt_keys()


def test_prompt_b_differs_substantially_from_prompt_a() -> None:
    a = get_hybrid_prompt("global_v21")
    b = get_hybrid_prompt("global_v21_b")
    assert a != b
    assert "Conservative" in b or "conservative" in b.lower()
    assert "INSUFFICIENT_EVIDENCE" in b


def test_openai_profile_uses_openai_variant_for_global_v21() -> None:
    gemini_text = get_hybrid_prompt("global_v21", "gemini")
    openai_text = get_hybrid_prompt("global_v21", "openai")
    assert gemini_text == get_hybrid_prompt("global_v21", None)
    assert openai_text != gemini_text
    assert "NEVER return quantity = 0" in openai_text
    assert "Warehouse aisle images" in openai_text or "warehouse aisle images" in openai_text.lower()


def test_non_openai_providers_use_default_variant() -> None:
    default_a = get_hybrid_prompt("global_v21")
    assert get_hybrid_prompt("global_v21", "gemini") == default_a
    assert get_hybrid_prompt("global_v21", "unknown_vendor") == default_a


def test_openai_global_v21_b_differs_from_default_b() -> None:
    d = get_hybrid_prompt("global_v21_b", "gemini")
    o = get_hybrid_prompt("global_v21_b", "openai")
    assert d != o
    assert "INSUFFICIENT_EVIDENCE" in d
    assert "over-abstain" in o.lower() or "models" in o.lower()
