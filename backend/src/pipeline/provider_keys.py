"""Pipeline provider key normalization (no registry / LLM adapter imports)."""

from __future__ import annotations

from typing import Any


def normalize_pipeline_provider_key(
    provider_name: str | None,
    settings: Any,
) -> str:
    """
    Effective provider key for this run.

    Prefer explicit ``provider_name`` (e.g. from inventory job). Otherwise use ``settings.llm_provider``.

    **Phase 7:** ``settings`` stays ``Any`` so callers may pass full ``AppSettings``, partial test
    doubles, or ``MagicMock``; only ``llm_provider`` is read (via ``getattr`` with a string default).
    """
    from src.pipeline.providers.definitions import is_pipeline_provider_active

    raw = (provider_name or "").strip().lower()
    if raw:
        return raw if is_pipeline_provider_active(raw) else "gemini"
    sp = getattr(settings, "llm_provider", "gemini") or "gemini"
    key = str(sp).strip().lower()
    return key if is_pipeline_provider_active(key) else "gemini"
