"""DeepSeek executor — multimodal guardrail, OpenAI-compatible client wiring (Phase 9)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.llm.deepseek_sdk_adapter import DeepSeekSdkAdapter
from src.llm.errors import LLMProviderError
from src.llm.openai_sdk_adapter import OpenAiSdkAdapter
from src.llm.types import LLMRequest, LLMResponse


def _settings_deepseek() -> MagicMock:
    s = MagicMock()
    s.deepseek_api_key = "sk-ds-test"
    s.deepseek_model = "deepseek-chat"
    s.deepseek_api_base_url = "https://api.deepseek.com"
    s.deepseek_request_timeout_sec = 60.0
    s.deepseek_vision_max_image_side = 2048
    s.hybrid_prompt = "global_v21"
    return s


def test_deepseek_blocks_multimodal_when_frames_nd_present() -> None:
    adapter = DeepSeekSdkAdapter()
    s = _settings_deepseek()
    req = LLMRequest(
        job_id="job-frames",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={"deepseek_model_name": "deepseek-chat"},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(req, s)
    assert ei.value.code == "UNSUPPORTED_MULTIMODAL_PROVIDER"
    assert "image-based" in ei.value.message.lower()
    assert ei.value.details.get("provider") == "deepseek"
    assert ei.value.details.get("model") == "deepseek-chat"
    assert ei.value.details.get("job_id") == "job-frames"


def test_deepseek_blocks_multimodal_when_context_images_present() -> None:
    adapter = DeepSeekSdkAdapter()
    s = _settings_deepseek()
    req = LLMRequest(
        job_id="job-ctx",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=None,
        context_images=[np.zeros((4, 4, 3), dtype=np.uint8)],
    )
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(req, s)
    assert ei.value.code == "UNSUPPORTED_MULTIMODAL_PROVIDER"


def test_deepseek_blocks_multimodal_when_frame_paths_present() -> None:
    adapter = DeepSeekSdkAdapter()
    s = _settings_deepseek()
    req = LLMRequest(
        job_id="job-paths",
        frames=[Path("/tmp/fake-frame.jpg")],
        frame_refs=["ref1"],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=None,
    )
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(req, s)
    assert ei.value.code == "UNSUPPORTED_MULTIMODAL_PROVIDER"


def test_deepseek_sdk_adapter_not_configured_without_api_key_text_only() -> None:
    """No images: guard passes through; parent rejects missing API key."""
    adapter = DeepSeekSdkAdapter()
    s = _settings_deepseek()
    s.deepseek_api_key = ""
    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={},
    )
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(req, s)
    assert ei.value.code == "NOT_CONFIGURED"
    assert ei.value.details.get("provider") == "deepseek"


def test_deepseek_text_only_delegates_to_openai_parent_execute() -> None:
    """Text-only request: multimodal guard does not run; parent execute is invoked."""
    adapter = DeepSeekSdkAdapter()
    settings = _settings_deepseek()
    req = LLMRequest(
        job_id="j-text",
        frames=[],
        frame_refs=[],
        prompt="Task for DeepSeek.",
        schema_version="v2.1",
        metadata={"deepseek_model_name": "deepseek-reasoner"},
    )
    fake = LLMResponse(
        provider="deepseek",
        model="deepseek-reasoner",
        latency_ms=1,
        parsed_json={"total_entities_detected": 0, "entities": []},
    )
    with patch.object(OpenAiSdkAdapter, "execute", return_value=fake) as parent_exec:
        out = adapter.execute(req, settings)
    parent_exec.assert_called_once()
    assert out.provider == "deepseek"
    assert out.model == "deepseek-reasoner"


def test_deepseek_text_only_no_frames_raises_no_frames_from_parent() -> None:
    adapter = DeepSeekSdkAdapter()
    settings = _settings_deepseek()
    req = LLMRequest(
        job_id="j-empty",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={},
    )
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(req, settings)
    assert ei.value.code == "NO_FRAMES"


def test_openai_adapter_unaffected_by_deepseek_multimodal_guard() -> None:
    """Regression: OpenAI path still accepts frames (DeepSeek guard is DeepSeek-only)."""
    from src.llm.openai_sdk_adapter import OpenAiSdkAdapter as OpenAIAdapter

    adapter = OpenAIAdapter()
    settings = MagicMock()
    settings.openai_api_key = "sk-openai-test"
    settings.openai_model = "gpt-4o-mini"
    settings.openai_request_timeout_sec = 60.0
    settings.openai_vision_max_image_side = 512
    settings.hybrid_prompt = "global_v21"
    ok_json = '{"total_entities_detected": 0, "entities": []}'
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content=ok_json))]
    mock_completion.usage = None
    req = LLMRequest(
        job_id="j-openai",
        frames=[],
        frame_refs=["f0"],
        prompt="Analyze.",
        schema_version="v2.1",
        metadata={"openai_model_name": "gpt-4o-mini"},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )
    with patch("src.llm.openai_sdk_adapter.OpenAI") as client_cls:
        client_inst = MagicMock()
        client_inst.chat.completions.create.return_value = mock_completion
        client_cls.return_value = client_inst
        out = adapter.execute(req, settings)
    assert out.provider == "openai"
    client_inst.chat.completions.create.assert_called_once()
