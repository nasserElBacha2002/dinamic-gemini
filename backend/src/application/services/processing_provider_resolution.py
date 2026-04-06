"""Resolve and validate explicit processing provider selection (Phase 5)."""

from __future__ import annotations

from typing import Any, Optional

from src.application.errors import ProcessingProviderNotConfiguredError, UnknownProcessingProviderError
from src.pipeline.providers.registry import (
    normalize_pipeline_provider_key,
    registered_pipeline_provider_keys,
)


def resolve_start_processing_provider(
    requested_provider_name: Optional[str],
    settings: Any,
) -> tuple[str, str]:
    """
    Return ``(pipeline_provider_key, prompt_key)`` for a new process-aisle job.

    * If ``requested_provider_name`` is empty/whitespace/None, use
      ``normalize_pipeline_provider_key(None, settings)`` (legacy default). No proactive
      credential check — same as pre–Phase 5 deferred failures at LLM time.
    * If non-empty, the key must be registered; required credentials for that provider must
      be present or we raise ``ProcessingProviderNotConfiguredError``.
    """
    raw = (requested_provider_name or "").strip()
    if not raw:
        key = normalize_pipeline_provider_key(None, settings)
    else:
        key = raw.lower()
        known = registered_pipeline_provider_keys()
        if key not in known:
            raise UnknownProcessingProviderError(
                f"Unknown processing provider {key!r}. Known keys: {sorted(known)}"
            )
        _ensure_explicit_provider_configured(key, settings)

    prompt_key = str(getattr(settings, "hybrid_prompt", "") or "default")
    return key, prompt_key


def _ensure_explicit_provider_configured(key: str, settings: Any) -> None:
    if key == "gemini":
        if not (getattr(settings, "gemini_api_key", "") or "").strip():
            raise ProcessingProviderNotConfiguredError(
                "Gemini is not configured (GEMINI_API_KEY is missing)."
            )
    elif key == "openai":
        if not (getattr(settings, "openai_api_key", "") or "").strip():
            raise ProcessingProviderNotConfiguredError(
                "OpenAI is not configured (OPENAI_API_KEY is missing)."
            )
