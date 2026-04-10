"""DeepSeek executor — OpenAI-compatible client wiring, logical provider + metadata keys (Phase 9)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.llm.deepseek_sdk_adapter import DeepSeekSdkAdapter
from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest


def _settings_deepseek() -> MagicMock:
    s = MagicMock()
    s.deepseek_api_key = "sk-ds-test"
    s.deepseek_model = "deepseek-chat"
    s.deepseek_api_base_url = "https://api.deepseek.com"
    s.deepseek_request_timeout_sec = 60.0
    s.deepseek_vision_max_image_side = 2048
    s.hybrid_prompt = "global_v21"
    return s


def test_deepseek_sdk_adapter_not_configured_without_api_key() -> None:
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
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(req, s)
    assert ei.value.code == "NOT_CONFIGURED"
    assert ei.value.details.get("provider") == "deepseek"


def test_deepseek_sdk_adapter_uses_job_model_and_sets_openai_client_base_url() -> None:
    adapter = DeepSeekSdkAdapter()
    settings = _settings_deepseek()
    ok_json = '{"total_entities_detected": 0, "entities": []}'
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content=ok_json))]
    mock_completion.usage = None

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="Task for DeepSeek.",
        schema_version="v2.1",
        metadata={"deepseek_model_name": "deepseek-vl2"},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )

    with patch("src.llm.openai_sdk_adapter.OpenAI") as client_cls:
        client_inst = MagicMock()
        client_inst.chat.completions.create.return_value = mock_completion
        client_cls.return_value = client_inst
        out = adapter.execute(req, settings)
        assert out.provider == "deepseek"
        assert out.model == "deepseek-vl2"
        client_cls.assert_called_once()
        call_kw = client_cls.call_args.kwargs
        assert call_kw.get("base_url") == "https://api.deepseek.com"
        assert call_kw.get("api_key") == "sk-ds-test"
        cc_kw = client_inst.chat.completions.create.call_args.kwargs
        assert cc_kw["model"] == "deepseek-vl2"
        content = cc_kw["messages"][0]["content"]
        assert content[0]["type"] == "text"
        assert "Task for DeepSeek" in content[0]["text"]
        assert sum(1 for p in content if p.get("type") == "image_url") == 1


def test_deepseek_sdk_adapter_maps_schema_invalid() -> None:
    adapter = DeepSeekSdkAdapter()
    settings = _settings_deepseek()
    bad = '{"total_entities_detected": 1, "entities": [{"entity_type": "INVALID"}]}'
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content=bad))]
    mock_completion.usage = None

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )

    with patch("src.llm.openai_sdk_adapter.OpenAI") as client_cls:
        client_inst = MagicMock()
        client_inst.chat.completions.create.return_value = mock_completion
        client_cls.return_value = client_inst
        with pytest.raises(LLMProviderError) as ei:
            adapter.execute(req, settings)
        assert ei.value.code == "SCHEMA_INVALID"
        assert ei.value.details.get("provider") == "deepseek"
