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
