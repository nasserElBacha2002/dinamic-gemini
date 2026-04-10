"""Anthropic (Claude) native executor — config, multimodal payload, model metadata, error mapping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.llm.anthropic_sdk_adapter import AnthropicSdkAdapter, _extract_json_text
from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest


def _settings_claude() -> MagicMock:
    s = MagicMock()
    s.anthropic_api_key = "sk-ant-test"
    s.anthropic_model = "claude-sonnet-4-20250514"
    s.anthropic_request_timeout_sec = 60.0
    s.anthropic_vision_max_image_side = 2048
    s.anthropic_max_output_tokens = 8192
    s.hybrid_prompt = "global_v21"
    return s


def test_anthropic_sdk_adapter_not_configured_without_api_key() -> None:
    adapter = AnthropicSdkAdapter()
    s = _settings_claude()
    s.anthropic_api_key = ""
    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(req, s)
    assert ei.value.code == "NOT_CONFIGURED"


def test_anthropic_sdk_adapter_uses_job_model_from_metadata() -> None:
    adapter = AnthropicSdkAdapter()
    settings = _settings_claude()
    ok_json = '{"total_entities_detected": 0, "entities": []}'
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = ok_json
    mock_message = MagicMock()
    mock_message.content = [text_block]
    mock_message.usage = MagicMock(input_tokens=10, output_tokens=5)

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="Analyze these aisle images.",
        schema_version="v2.1",
        metadata={"claude_model_name": "claude-3-5-sonnet-20241022"},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )

    with patch("anthropic.Anthropic") as client_cls:
        client_inst = MagicMock()
        client_inst.messages.create.return_value = mock_message
        client_cls.return_value = client_inst
        out = adapter.execute(req, settings)
        assert out.model == "claude-3-5-sonnet-20241022"
        assert out.provider == "claude"
        call_kw = client_inst.messages.create.call_args.kwargs
        assert call_kw["model"] == "claude-3-5-sonnet-20241022"
        user_content = call_kw["messages"][0]["content"]
        assert user_content[0]["type"] == "text"
        assert "Analyze these aisle images" in user_content[0]["text"]
        assert sum(1 for p in user_content if p.get("type") == "image") == 1


def test_anthropic_sdk_adapter_maps_schema_invalid() -> None:
    adapter = AnthropicSdkAdapter()
    settings = _settings_claude()
    bad = '{"total_entities_detected": 1, "entities": [{"entity_type": "INVALID"}]}'
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = bad
    mock_message = MagicMock()
    mock_message.content = [text_block]
    mock_message.usage = None

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )

    with patch("anthropic.Anthropic") as client_cls:
        client_inst = MagicMock()
        client_inst.messages.create.return_value = mock_message
        client_cls.return_value = client_inst
        with pytest.raises(LLMProviderError) as ei:
            adapter.execute(req, settings)
        assert ei.value.code == "SCHEMA_INVALID"


def test_anthropic_sdk_adapter_maps_invalid_json() -> None:
    adapter = AnthropicSdkAdapter()
    settings = _settings_claude()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "not json"
    mock_message = MagicMock()
    mock_message.content = [text_block]
    mock_message.usage = None

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )

    with patch("anthropic.Anthropic") as client_cls:
        client_inst = MagicMock()
        client_inst.messages.create.return_value = mock_message
        client_cls.return_value = client_inst
        with pytest.raises(LLMProviderError) as ei:
            adapter.execute(req, settings)
        assert ei.value.code == "INVALID_JSON"


def test_extract_json_text_strips_markdown_fence_claude() -> None:
    raw = '```json\n{"total_entities_detected": 0, "entities": []}\n```'
    t = _extract_json_text(raw)
    assert '"entities"' in t
    assert not t.startswith("```")
