"""
Phase 4 closure — architectural boundaries (registry, no SDK in orchestrator).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.llm.gemini_sdk_adapter import GeminiSdkAdapter
from src.llm.openai_sdk_adapter import OpenAiSdkAdapter
from src.llm.types import LLMRequest, LLMResponse
from src.pipeline.providers.registry import resolve_llm_executor


def _minimal_request() -> LLMRequest:
    return LLMRequest(
        job_id="j",
        frames=[],
        frame_refs=[],
        prompt="",
        schema_version="v2.1",
        metadata={},
    )


def test_openai_uses_native_openai_sdk_adapter() -> None:
    settings = MagicMock()
    ex = resolve_llm_executor("openai", settings)
    assert isinstance(ex, OpenAiSdkAdapter)


def test_gemini_uses_native_gemini_sdk_adapter() -> None:
    settings = MagicMock()
    settings.gemini_api_key = "k"
    ex = resolve_llm_executor("gemini", settings)
    assert isinstance(ex, GeminiSdkAdapter)


def test_llm_request_response_have_no_gemini_specific_attributes() -> None:
    """Contract neutrality: public fields are generic (historical class names only)."""
    req = _minimal_request()
    public = {a for a in dir(req) if not a.startswith("_")}
    assert not any("gemini" in a.lower() for a in public)
    resp = LLMResponse(provider="openai", model=None, latency_ms=0, parsed_json={"total_entities_detected": 0, "entities": []})
    public_r = {a for a in dir(resp) if not a.startswith("_")}
    assert not any("gemini" in a.lower() for a in public_r)


def test_provider_registry_has_no_top_level_vendor_adapter_imports() -> None:
    """Adapters load inside ``resolve_llm_executor`` (indented imports), not at registry module scope."""
    import src.pipeline.providers.registry as reg

    text = Path(reg.__file__).read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line or line[:1].isspace():
            continue
        s = line.strip()
        if s.startswith("from src.llm.gemini_sdk_adapter import") or s.startswith(
            "from src.llm.openai_sdk_adapter import"
        ):
            raise AssertionError(f"Registry must lazy-import vendor adapters: {line!r}")


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
