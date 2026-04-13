"""Anthropic (Claude) native executor — config, multimodal payload, model metadata, error mapping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import numpy as np
import pytest
from anthropic import APIStatusError

from src.llm.anthropic_sdk_adapter import (
    AnthropicSdkAdapter,
    _extract_json_text,
    classify_anthropic_messages_api_error,
)
from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest


def _settings_claude() -> MagicMock:
    s = MagicMock()
    s.anthropic_api_key = "sk-ant-test"
    s.anthropic_model = "claude-sonnet-4-20250514"
    s.anthropic_request_timeout_sec = 60.0
    s.anthropic_vision_max_image_side = 2048
    s.anthropic_max_output_tokens = 8192
    s.anthropic_max_retries = 4
    s.anthropic_retry_base_delay_sec = 0.01
    s.hybrid_prompt = "global_v21"
    return s


def _api_status_error(status: int, *, body: dict | None = None, message: str = "err") -> APIStatusError:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    r = httpx.Response(status, request=req)
    return APIStatusError(message, response=r, body=body or {})


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


def test_classify_529_overloaded_error_maps_provider_overloaded() -> None:
    exc = _api_status_error(
        529,
        body={
            "type": "overloaded_error",
            "message": "Overloaded",
            "request_id": "req_011Ca1p5a2xct1R6bDhoHjVH",
        },
        message="Overloaded",
    )
    code, det = classify_anthropic_messages_api_error(exc)
    assert code == "PROVIDER_OVERLOADED"
    assert det["http_status"] == 529
    assert det["api_error_type"] == "overloaded_error"
    assert det["request_id"] == "req_011Ca1p5a2xct1R6bDhoHjVH"
    assert det["provider_family"] == "anthropic"


def test_classify_401_not_retryable_not_overloaded() -> None:
    exc = _api_status_error(401, body={"type": "authentication_error"}, message="bad key")
    code, det = classify_anthropic_messages_api_error(exc)
    assert code == "NOT_CONFIGURED"
    assert det["http_status"] == 401


def test_classify_timeout_signal_maps_timeout() -> None:
    for msg in ("connection timed out", "Read timeout after 30s"):
        code, _det = classify_anthropic_messages_api_error(Exception(msg))
        assert code == "TIMEOUT", msg


def test_anthropic_retries_529_then_succeeds() -> None:
    adapter = AnthropicSdkAdapter()
    settings = _settings_claude()
    settings.anthropic_max_retries = 3
    ok_json = '{"total_entities_detected": 0, "entities": []}'
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = ok_json
    mock_message = MagicMock()
    mock_message.content = [text_block]
    mock_message.usage = None

    overload = _api_status_error(
        529,
        body={"type": "overloaded_error", "request_id": "req_retry_chain"},
        message="Overloaded",
    )

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
        client_inst.messages.create.side_effect = [overload, mock_message]
        client_cls.return_value = client_inst
        with patch("time.sleep"):
            out = adapter.execute(req, settings)
        assert out.provider == "claude"
        assert client_inst.messages.create.call_count == 2


def test_anthropic_retries_429_then_succeeds() -> None:
    adapter = AnthropicSdkAdapter()
    settings = _settings_claude()
    settings.anthropic_max_retries = 3
    ok_json = '{"total_entities_detected": 0, "entities": []}'
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = ok_json
    mock_message = MagicMock()
    mock_message.content = [text_block]
    mock_message.usage = None

    rate_limited = _api_status_error(
        429,
        body={"type": "rate_limit_error", "message": "Too many requests"},
        message="Rate limited",
    )

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
        client_inst.messages.create.side_effect = [rate_limited, mock_message]
        client_cls.return_value = client_inst
        with patch("time.sleep"):
            out = adapter.execute(req, settings)
        assert out.provider == "claude"
        assert client_inst.messages.create.call_count == 2


def test_anthropic_exhausts_retries_on_529_raises_provider_overloaded() -> None:
    adapter = AnthropicSdkAdapter()
    settings = _settings_claude()
    settings.anthropic_max_retries = 2
    overload = _api_status_error(
        529,
        body={"type": "overloaded_error", "request_id": "req_final"},
        message="Overloaded",
    )
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
        client_inst.messages.create.side_effect = overload
        client_cls.return_value = client_inst
        with patch("time.sleep"):
            with pytest.raises(LLMProviderError) as ei:
                adapter.execute(req, settings)
    assert ei.value.code == "PROVIDER_OVERLOADED"
    assert ei.value.details.get("request_id") == "req_final"
    assert ei.value.details.get("retryable_class") is True
    assert client_inst.messages.create.call_count == 2


def test_anthropic_exhausts_retries_on_429_raises_rate_limit() -> None:
    adapter = AnthropicSdkAdapter()
    settings = _settings_claude()
    settings.anthropic_max_retries = 3
    rate_limited = _api_status_error(
        429,
        body={"type": "rate_limit_error", "request_id": "req_rl"},
        message="Rate limited",
    )
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
        client_inst.messages.create.side_effect = rate_limited
        client_cls.return_value = client_inst
        with patch("time.sleep"):
            with pytest.raises(LLMProviderError) as ei:
                adapter.execute(req, settings)
    assert ei.value.code == "RATE_LIMIT"
    assert ei.value.details.get("retryable_class") is True
    assert client_inst.messages.create.call_count == 3


def test_anthropic_max_retries_one_single_call_no_sleep_on_overload() -> None:
    adapter = AnthropicSdkAdapter()
    settings = _settings_claude()
    settings.anthropic_max_retries = 1
    overload = _api_status_error(
        529,
        body={"type": "overloaded_error", "request_id": "req_one"},
        message="Overloaded",
    )
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
        client_inst.messages.create.side_effect = overload
        client_cls.return_value = client_inst
        with patch("time.sleep") as sl:
            with pytest.raises(LLMProviderError) as ei:
                adapter.execute(req, settings)
    assert ei.value.code == "PROVIDER_OVERLOADED"
    assert client_inst.messages.create.call_count == 1
    sl.assert_not_called()


def test_anthropic_auth_error_not_retried() -> None:
    adapter = AnthropicSdkAdapter()
    settings = _settings_claude()
    settings.anthropic_max_retries = 4
    auth_exc = _api_status_error(401, body={"type": "authentication_error"}, message="nope")
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
        client_inst.messages.create.side_effect = auth_exc
        client_cls.return_value = client_inst
        with patch("time.sleep") as sl:
            with pytest.raises(LLMProviderError) as ei:
                adapter.execute(req, settings)
    assert ei.value.code == "NOT_CONFIGURED"
    assert client_inst.messages.create.call_count == 1
    sl.assert_not_called()
