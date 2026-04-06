"""Discoverable models and prompt profiles for aisle processing experiments (Phase 5)."""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple

from src.llm.prompts import registered_hybrid_prompt_keys

_ModelPair = Tuple[str, str]


def _split_csv(raw: str) -> List[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def models_for_provider(provider_key: str, settings: Any) -> List[_ModelPair]:
    """Return (model_id, short_label) pairs offered for the given pipeline provider."""
    key = (provider_key or "").strip().lower()
    if key == "gemini":
        ids = _split_csv(getattr(settings, "processing_gemini_models", "") or "")
        if not ids:
            ids = [getattr(settings, "gemini_model_name", "gemini-2.0-flash-exp")]
        return [(m, m) for m in ids]
    if key == "openai":
        ids = _split_csv(getattr(settings, "processing_openai_models", "") or "")
        if not ids:
            ids = [getattr(settings, "openai_model", "gpt-4o")]
        return [(m, m) for m in ids]
    if key == "fake":
        return [("fixture", "Fixture (deterministic JSON, no network)")]
    return []


def default_model_for_provider(provider_key: str, settings: Any) -> str | None:
    """Default model id when the client omits model_name (per-provider settings)."""
    key = (provider_key or "").strip().lower()
    if key == "gemini":
        return str(getattr(settings, "gemini_model_name", "") or "gemini-2.0-flash-exp").strip()
    if key == "openai":
        return str(getattr(settings, "openai_model", "") or "gpt-4o").strip()
    if key == "fake":
        return "fixture"
    return None


def normalize_requested_model(provider_key: str, requested: str | None, settings: Any) -> str | None:
    """Return canonical model id or None if invalid for provider."""
    allowed = {m for m, _ in models_for_provider(provider_key, settings)}
    if not allowed:
        return None
    raw = (requested or "").strip()
    if not raw:
        dm = default_model_for_provider(provider_key, settings)
        return dm if dm in allowed else sorted(allowed)[0]
    if raw in allowed:
        return raw
    return None


def prompt_profile_catalog() -> List[Tuple[str, str, str]]:
    """(key, label, description) for API options."""
    return [
        (
            "global_v21",
            "Prompt A — standard scan (global_v21)",
            "Balanced entity detection; default production profile.",
        ),
        (
            "global_v21_b",
            "Prompt B — conservative / anti-hallucination (global_v21_b)",
            "Stricter abstention, nulls when uncertain, INSUFFICIENT_EVIDENCE when views are ambiguous.",
        ),
    ]


def is_valid_prompt_key(key: str, _settings: Any) -> bool:
    del _settings  # reserved for future env-gated keys
    return key in registered_hybrid_prompt_keys()


def default_prompt_key(settings: Any) -> str:
    return str(getattr(settings, "hybrid_prompt", "") or "global_v21").strip() or "global_v21"
