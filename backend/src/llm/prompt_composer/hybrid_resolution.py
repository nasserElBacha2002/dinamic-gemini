"""
Provider policy overlay for hybrid registry entries (``default`` vs ``openai`` branch).

**Overlay rules:**
* ``openai`` (when ``prompt_parity_mode`` is false) selects the ``openai`` **replacement** fragment.
* ``claude`` (when ``prompt_parity_mode`` is false) appends the registry ``claude`` supplement to the
  ``default`` body (canonical JSON entity contract for text models). Gemini, DeepSeek, and unknown
  keys use ``default`` only.
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

from typing import Dict, Final, Optional, Union

from src.llm.prompt_composer.hybrid_profiles import PROMPTS


def _hybrid_default_text(entry: Union[str, Dict[str, str]]) -> Optional[str]:
    """Return the default-branch hybrid string with trailing whitespace stripped (matches ``compose_base``)."""
    if isinstance(entry, str):
        return entry.rstrip()
    if isinstance(entry, dict) and isinstance(entry.get("default"), str):
        return str(entry["default"]).rstrip()
    return None


HYBRID_PROMPTS: Final[Dict[str, str]] = {
    k: dv for k, v in PROMPTS.items() if (dv := _hybrid_default_text(v)) is not None
}


def registered_hybrid_prompt_keys() -> frozenset[str]:
    """Keys accepted for per-job hybrid prompt selection (API / processing)."""
    return frozenset(HYBRID_PROMPTS.keys())


def resolve_hybrid_entry_for_provider(
    entry: Union[str, Dict[str, str]],
    provider_key: Optional[str],
    *,
    prompt_parity_mode: bool = False,
) -> str:
    """
    Resolve one registry entry to the text sent as the hybrid **base** prompt (before enrichments).

    * If ``provider_key`` is exactly ``openai`` (case-insensitive), the entry defines an ``openai``
      string, and ``prompt_parity_mode`` is false, the ``openai`` fragment **replaces** ``default``.
    * If ``prompt_parity_mode`` is true, the ``openai`` fragment is never used.
    * If ``provider_key`` is exactly ``claude`` (case-insensitive), the entry defines a non-empty
      ``claude`` string, and ``prompt_parity_mode`` is false, that string is **appended** after the
      ``default`` body (canonical entity JSON contract). Otherwise Claude resolution falls through
      to ``default`` only (same as Gemini when parity mode is on).
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
                pk == "openai"
                and not prompt_parity_mode
                and isinstance(entry.get("openai"), str)
            )
            if use_openai_overlay:
                return str(entry["openai"]).rstrip()
            use_claude_supplement = (
                pk == "claude"
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
