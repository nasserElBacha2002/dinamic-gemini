"""
Provider policy overlay for hybrid registry entries (``default`` vs ``openai`` branch).

**Overlay rule:** only the literal key ``openai`` selects the ``openai`` fragment. Every other
registered pipeline key (``gemini``, ``claude``, future vendors, ``None``, etc.) uses the
``default`` fragment. Adding a new overlay key later (e.g. a ``claude`` fragment in ``PROMPTS``)
must not change text for ``openai``, ``gemini``, or existing defaults unless explicitly versioned.

**Phase 8 — Claude prompt policy (intentional, not permanent):** Claude uses the **same**
``default`` branch as Gemini. That is a deliberate Phase 8 choice to ship a first-class executor
without duplicating prompt bodies. A Claude-specific overlay may be introduced in a later phase;
resolution logic here already isolates overlay selection so that future change stays localized.

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
) -> str:
    """
    Resolve one registry entry to the text sent as the hybrid **base** prompt (before enrichments).

    * If ``provider_key`` is exactly ``openai`` (case-insensitive) and the entry defines an
      ``openai`` string, that variant is used.
    * Every other key (``gemini``, ``claude``, unknown, ``None``, etc.) uses the ``default``
      fragment — including Claude in Phase 8 (see module docstring).

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
            return resolve_hybrid_entry_for_provider(PROMPTS["global_v21"], None)
        if isinstance(entry.get("default"), str):
            if pk == "openai" and isinstance(entry.get("openai"), str):
                return str(entry["openai"]).rstrip()
            return str(entry["default"]).rstrip()
    return resolve_hybrid_entry_for_provider(PROMPTS["global_v21"], None)
