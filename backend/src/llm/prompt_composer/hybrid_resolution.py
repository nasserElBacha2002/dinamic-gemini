"""
Provider policy overlay for hybrid registry entries (``default`` vs ``openai`` branch).

**Phase E1:** These overlays are **ProviderPromptRules** (non–supplier-editable). Protected base
fragments live in ``hybrid_profiles``; stable substring markers for regression tests are defined in
``protected_prompt_contract``.

**Overlay rules:**
* ``openai`` (when ``prompt_parity_mode`` is false) selects the ``openai`` **replacement** fragment.
* ``claude`` (when ``prompt_parity_mode`` is false) appends the registry ``claude`` supplement to the
  ``default`` body (canonical JSON entity contract for text models). The same supplement applies when
  the key normalizes to Claude family: ``anthropic`` or any string starting with ``claude`` (e.g.
  model slugs). Gemini, DeepSeek, and unknown keys use ``default`` only.
* ``prompt_parity_mode`` disables both ``openai`` and ``claude`` overlays so comparison runs share
  the same base text as Gemini.

**Phase 9 — DeepSeek:** Same as Claude/Gemini for hybrid **base** text: ``deepseek`` uses the
``default`` fragment only (OpenAI overlay is keyed solely by ``openai``).

**Pre-Phase 10 — prompt parity mode:** When ``prompt_parity_mode`` is true, the ``openai`` overlay
is **not** selected even if ``provider_key == \"openai\"``; the ``default`` fragment is used so
OpenAI matches Gemini/Claude/DeepSeek base text for fair multi-provider comparison. Default is false
(production preserves historical OpenAI overlay behavior).

**Phase 6:** prompt traceability belongs at enrichment / request-assembly layers, not here;
this module stays pure string resolution.
"""

from __future__ import annotations

from typing import Final

from src.llm.prompt_composer.hybrid_profiles import PROMPTS


def _normalized_key_for_claude_hybrid_supplement(raw: str) -> str:
    """Map vendor/model hints to ``claude`` for hybrid supplement selection only (OpenAI branch unchanged)."""
    if raw == "anthropic" or raw.startswith("claude"):
        return "claude"
    return raw


def _hybrid_default_text(entry: str | dict[str, str]) -> str | None:
    """Return the default-branch hybrid string with trailing whitespace stripped (matches ``compose_base``)."""
    if isinstance(entry, str):
        return entry.rstrip()
    if isinstance(entry, dict) and isinstance(entry.get("default"), str):
        return str(entry["default"]).rstrip()
    return None


HYBRID_PROMPTS: Final[dict[str, str]] = {
    k: dv for k, v in PROMPTS.items() if (dv := _hybrid_default_text(v)) is not None
}


def registered_hybrid_prompt_keys() -> frozenset[str]:
    """Keys accepted for per-job hybrid prompt selection (API / processing)."""
    return frozenset(HYBRID_PROMPTS.keys())


def resolve_hybrid_entry_for_provider(
    entry: str | dict[str, str],
    provider_key: str | None,
    *,
    prompt_parity_mode: bool = False,
) -> str:
    """
    Resolve one registry entry to the text sent as the hybrid **base** prompt (before enrichments).

    * If ``provider_key`` is exactly ``openai`` (case-insensitive), the entry defines an ``openai``
      string, and ``prompt_parity_mode`` is false, the ``openai`` fragment **replaces** ``default``.
    * If ``prompt_parity_mode`` is true, the ``openai`` fragment is never used.
    * If the key is ``claude`` after Claude-family normalization (``claude``, ``anthropic``, or
      ``claude-…`` prefixes), the entry defines a non-empty ``claude`` string, and
      ``prompt_parity_mode`` is false, that string is **appended** after the ``default`` body.
      Otherwise resolution falls through to ``default`` only (same as Gemini when parity mode is on).
    * Keys ``gemini``, ``deepseek``, ``None``, etc. use the ``default`` fragment only (no append).

    Legacy ``PROMPTS`` rows that use ``system``/``user`` (non-hybrid) are not valid hybrid entries;
    for backward compatibility they fall back to **global_v21 default** text only, with **no** OpenAI
    overlay (``provider_key`` ignored for that fallback).

    All returned strings are ``.rstrip()``'d for wire consistency with historical behavior.
    """
    pk = (provider_key or "").strip().lower()
    if isinstance(entry, str):
        return entry.rstrip()
    if isinstance(entry, dict):
        if "system" in entry:
            return resolve_hybrid_entry_for_provider(
                PROMPTS["global_v21"], None, prompt_parity_mode=prompt_parity_mode
            )
        if isinstance(entry.get("default"), str):
            default_text = str(entry["default"]).rstrip()
            use_openai_overlay = (
                pk == "openai" and not prompt_parity_mode and isinstance(entry.get("openai"), str)
            )
            if use_openai_overlay:
                return str(entry["openai"]).rstrip()
            claude_overlay_pk = _normalized_key_for_claude_hybrid_supplement(pk)
            use_claude_supplement = (
                claude_overlay_pk == "claude"
                and not prompt_parity_mode
                and isinstance(entry.get("claude"), str)
                and str(entry["claude"]).strip() != ""
            )
            if use_claude_supplement:
                return (default_text + "\n\n" + str(entry["claude"]).rstrip()).rstrip()
            return default_text
    return resolve_hybrid_entry_for_provider(
        PROMPTS["global_v21"], None, prompt_parity_mode=prompt_parity_mode
    )
