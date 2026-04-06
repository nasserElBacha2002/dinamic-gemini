"""
Phase 4 closure — architectural boundaries (registry, transitional bridge, no SDK in orchestrator).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.llm.gemini_sdk_adapter import GeminiSdkAdapter
from src.llm.openai_sdk_adapter import OpenAiSdkAdapter
from src.llm.types import LLMRequest, LLMResponse
from src.pipeline.providers.registry import (
    TRANSITIONAL_LLM_PROVIDER_BRIDGE_KEYS,
    TransitionalLlmProviderBridgeExecutor,
    resolve_llm_executor,
)


def _minimal_request() -> LLMRequest:
    return LLMRequest(
        job_id="j",
        frames=[],
        frame_refs=[],
        prompt="",
        schema_version="v2.1",
        metadata={},
    )


def test_transitional_bridge_keys_match_fake_only() -> None:
    assert TRANSITIONAL_LLM_PROVIDER_BRIDGE_KEYS == frozenset({"fake"})


def test_fake_uses_transitional_bridge_executor() -> None:
    settings = MagicMock()
    settings.fake_llm_fixture_path = None
    ex = resolve_llm_executor("fake", settings)
    assert isinstance(ex, TransitionalLlmProviderBridgeExecutor)


def test_openai_uses_native_openai_sdk_adapter() -> None:
    settings = MagicMock()
    ex = resolve_llm_executor("openai", settings)
    assert isinstance(ex, OpenAiSdkAdapter)
    assert not isinstance(ex, TransitionalLlmProviderBridgeExecutor)


def test_gemini_executor_is_not_transitional_bridge() -> None:
    settings = MagicMock()
    settings.gemini_api_key = "k"
    ex = resolve_llm_executor("gemini", settings)
    assert isinstance(ex, GeminiSdkAdapter)
    assert not isinstance(ex, TransitionalLlmProviderBridgeExecutor)


def test_llm_request_response_have_no_gemini_specific_attributes() -> None:
    """Contract neutrality: public fields are generic (historical class names only)."""
    req = _minimal_request()
    public = {a for a in dir(req) if not a.startswith("_")}
    assert not any("gemini" in a.lower() for a in public)
    resp = LLMResponse(provider="fake", model=None, latency_ms=0, parsed_json={"total_entities_detected": 0, "entities": []})
    public_r = {a for a in dir(resp) if not a.startswith("_")}
    assert not any("gemini" in a.lower() for a in public_r)


def test_hybrid_inventory_pipeline_module_has_no_vendor_sdk_imports() -> None:
    import src.pipeline.hybrid_inventory_pipeline as hip

    source = Path(hip.__file__).read_text(encoding="utf-8")
    assert "GeminiClient" not in source
    assert "GeminiGlobalAnalyzer" not in source


def test_analysis_stage_module_has_no_vendor_sdk_imports() -> None:
    import src.pipeline.stages.analysis_stage as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "GeminiClient" not in source
    assert "GeminiGlobalAnalyzer" not in source


def test_transitional_bridge_ignores_settings_on_execute_call() -> None:
    """Bridge forwards only ``request`` to ``analyze_global``; settings are construct-time."""
    inner = MagicMock()
    inner.analyze_global.return_value = LLMResponse(
        provider="fake", model=None, latency_ms=0, parsed_json={"total_entities_detected": 0, "entities": []}
    )
    bridge = TransitionalLlmProviderBridgeExecutor(inner)
    r = _minimal_request()
    bridge.execute(r, MagicMock(sentinel="different"))
    inner.analyze_global.assert_called_once_with(r)
