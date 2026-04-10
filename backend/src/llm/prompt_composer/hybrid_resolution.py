"""
Provider policy overlay for hybrid registry entries (``default`` vs ``openai`` branch).

**Parity-only model:** only the literal key ``openai`` selects the ``openai`` fragment; everything
else uses ``default``. This is **not** the long-term multi-vendor strategy — Claude, DeepSeek, etc.
must get explicit overlays in a later phase, not implicit mapping through this rule.

**Phase 6:** prompt traceability and audit hooks belong at enrichment / request-assembly layers, not
here; this module stays pure string resolution.
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

    **Parity-preserving provider model (Phase 4 only)** — not the final multi-vendor strategy:

    * If ``provider_key`` is exactly ``openai`` (case-insensitive) and the entry defines an
      ``openai`` string, that variant is used.
    * Every other provider key (``gemini``, unknown, ``None``, future vendors) uses the ``default``
      fragment.

    Legacy ``PROMPTS`` rows that use ``system``/``user`` (non-hybrid) are not valid hybrid entries;
    for backward compatibility they fall back to **global_v21 default** text only, with **no** OpenAI
    overlay (``provider_key`` ignored for that fallback). Future providers (e.g. Claude, DeepSeek)
    must not rely on this special-case; a future phase will replace overlay selection with an explicit
    policy map (see module docstring).

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
