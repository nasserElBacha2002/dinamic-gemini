"""Phase 4 — provider registry resolution and unknown-provider behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.llm.gemini_sdk_adapter import GeminiSdkAdapter
from src.pipeline.providers.registry import (
    UnknownPipelineProviderError,
    normalize_pipeline_provider_key,
    resolve_llm_executor,
)


def test_normalize_prefers_explicit_provider_name_over_settings() -> None:
    settings = MagicMock()
    settings.llm_provider = "fake"
    assert normalize_pipeline_provider_key("gemini", settings) == "gemini"


def test_normalize_falls_back_to_settings_llm_provider() -> None:
    settings = MagicMock()
    settings.llm_provider = "fake"
    assert normalize_pipeline_provider_key(None, settings) == "fake"


def test_resolve_gemini_returns_sdk_adapter() -> None:
    settings = MagicMock()
    ex = resolve_llm_executor("gemini", settings)
    assert isinstance(ex, GeminiSdkAdapter)


def test_resolve_fake_returns_delegate() -> None:
    settings = MagicMock()
    settings.fake_llm_fixture_path = None
    ex = resolve_llm_executor("fake", settings)
    req = MagicMock()
    req.frames = []
    req.frames_nd = None
    # FakeProvider returns minimal JSON without file/network
    from src.llm.types import LLMRequest

    r = LLMRequest(
        job_id="j",
        frames=[],
        frame_refs=[],
        prompt="",
        schema_version="v2.1",
        metadata={},
    )
    out = ex.execute(r, settings)
    assert out.provider == "fake"


def test_resolve_unknown_raises() -> None:
    with pytest.raises(UnknownPipelineProviderError):
        resolve_llm_executor("unknown_vendor_xyz", MagicMock())
