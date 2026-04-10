"""Provider policy overlay: pick ``default`` vs ``openai`` fragment for a hybrid registry entry."""

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


def _global_v21_default_text() -> str:
    g = PROMPTS["global_v21"]
    assert isinstance(g, dict)
    return str(g["default"]).rstrip()


def resolve_hybrid_entry_for_provider(
    entry: Union[str, Dict[str, str]],
    provider_key: Optional[str],
) -> str:
    """Pick provider-specific hybrid text when present; otherwise ``default`` or legacy fallback."""
    pk = (provider_key or "").strip().lower()
    if isinstance(entry, str):
        return entry.rstrip()
    if isinstance(entry, dict):
        if "system" in entry:
            return _global_v21_default_text()
        if isinstance(entry.get("default"), str):
            if pk == "openai" and isinstance(entry.get("openai"), str):
                return str(entry["openai"]).rstrip()
            return str(entry["default"]).rstrip()
    return _global_v21_default_text()
