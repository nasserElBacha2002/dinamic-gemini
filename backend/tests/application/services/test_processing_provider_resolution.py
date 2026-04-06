"""Phase 5 — explicit provider resolution for POST process."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.application.errors import ProcessingProviderNotConfiguredError, UnknownProcessingProviderError
from src.application.services.processing_provider_resolution import resolve_start_processing_provider


def test_resolve_omitted_uses_settings_default_without_credential_gate() -> None:
    settings = MagicMock()
    settings.llm_provider = "gemini"
    settings.hybrid_prompt = "global_v21"
    settings.gemini_api_key = ""
    settings.openai_api_key = ""
    key, prompt_key = resolve_start_processing_provider(None, settings)
    assert key == "gemini"
    assert prompt_key == "global_v21"


def test_resolve_empty_string_same_as_omitted() -> None:
    settings = MagicMock()
    settings.llm_provider = "fake"
    settings.hybrid_prompt = "default"
    settings.gemini_api_key = ""
    settings.openai_api_key = ""
    key, _pk = resolve_start_processing_provider("   ", settings)
    assert key == "fake"


def test_resolve_explicit_unknown_raises() -> None:
    settings = MagicMock()
    settings.hybrid_prompt = "x"
    with pytest.raises(UnknownProcessingProviderError):
        resolve_start_processing_provider("vendor-xyz", settings)


def test_resolve_explicit_gemini_without_key_raises() -> None:
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    settings.gemini_api_key = ""
    with pytest.raises(ProcessingProviderNotConfiguredError):
        resolve_start_processing_provider("gemini", settings)


def test_resolve_explicit_openai_without_key_raises() -> None:
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    settings.openai_api_key = ""
    with pytest.raises(ProcessingProviderNotConfiguredError):
        resolve_start_processing_provider("openai", settings)


def test_resolve_explicit_fake_never_requires_vendor_keys() -> None:
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    settings.gemini_api_key = ""
    settings.openai_api_key = ""
    key, pk = resolve_start_processing_provider("fake", settings)
    assert key == "fake"
    assert pk == "global_v21"
