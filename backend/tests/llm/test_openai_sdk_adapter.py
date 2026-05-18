"""OpenAI native executor — config, multimodal payload, model metadata, error mapping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.llm.errors import LLMProviderError
from src.llm.openai_sdk_adapter import OpenAiSdkAdapter, _extract_json_text
from src.llm.types import LLMRequest


def _settings_openai() -> MagicMock:
    s = MagicMock()
    s.openai_api_key = "sk-test"
    s.openai_model = "gpt-4o"
    s.openai_request_timeout_sec = 60.0
    s.openai_vision_max_image_side = 2048
    s.hybrid_prompt = "global_v21"
    return s


def test_openai_sdk_adapter_not_configured_without_api_key() -> None:
    adapter = OpenAiSdkAdapter()
    s = _settings_openai()
    s.openai_api_key = ""
    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["f0"],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(req, s)
    assert ei.value.code == "NOT_CONFIGURED"


def test_openai_sdk_adapter_uses_job_model_from_metadata() -> None:
    adapter = OpenAiSdkAdapter()
    settings = _settings_openai()
    ok_json = '{"total_entities_detected": 0, "entities": []}'
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content=ok_json))]
    mock_completion.usage = None

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["img_001"],
        prompt="Analyze these aisle images.",
        schema_version="v2.1",
        metadata={"openai_model_name": "gpt-4o-mini"},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )

    with patch("src.llm.openai_sdk_adapter.OpenAI") as client_cls:
        client_inst = MagicMock()
        client_inst.chat.completions.create.return_value = mock_completion
        client_cls.return_value = client_inst
        out = adapter.execute(req, settings)
        assert out.model == "gpt-4o-mini"
        assert out.provider == "openai"
        call_kw = client_inst.chat.completions.create.call_args.kwargs
        assert call_kw["model"] == "gpt-4o-mini"
        content = call_kw["messages"][0]["content"]
        assert content[0]["type"] == "text"
        assert "Analyze these aisle images" in content[0]["text"]
        assert sum(1 for p in content if p.get("type") == "image_url") == 1
        label_text = " ".join(p["text"] for p in content if p.get("type") == "text")
        assert "PRIMARY_EVIDENCE" in label_text
        assert "img_001" in label_text


def test_openai_sdk_adapter_includes_context_images_and_instruction() -> None:
    adapter = OpenAiSdkAdapter()
    settings = _settings_openai()
    ok_json = '{"total_entities_detected": 0, "entities": []}'
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content=ok_json))]
    mock_completion.usage = None

    pil = MagicMock()
    pil.mode = "RGB"
    pil.size = (10, 10)

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["prim-1"],
        prompt="Primary task.",
        schema_version="v2.1",
        metadata={"reference_image_ids": ["ref-1"]},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
        context_instruction="Reference context here.",
        context_images=[pil],
    )

    with patch("src.llm.openai_sdk_adapter.OpenAI") as client_cls:
        client_inst = MagicMock()
        client_inst.chat.completions.create.return_value = mock_completion
        client_cls.return_value = client_inst
        adapter.execute(req, settings)
        content = client_inst.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "Reference context here" in content[0]["text"]
        imgs = [p for p in content if p.get("type") == "image_url"]
        assert len(imgs) == 2
        label_text = " ".join(p["text"] for p in content if p.get("type") == "text")
        assert "REFERENCE_ONLY" in label_text
        assert "PRIMARY_EVIDENCE" in label_text


def test_openai_sdk_adapter_prompt_contract_requires_canonical_label_fields() -> None:
    adapter = OpenAiSdkAdapter()
    settings = _settings_openai()
    ok_json = '{"total_entities_detected": 0, "entities": []}'
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content=ok_json))]
    mock_completion.usage = None

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["f0"],
        prompt="Analyze aisle entities.",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )

    with patch("src.llm.openai_sdk_adapter.OpenAI") as client_cls:
        client_inst = MagicMock()
        client_inst.chat.completions.create.return_value = mock_completion
        client_cls.return_value = client_inst
        adapter.execute(req, settings)
        content = client_inst.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        text = content[0]["text"]
        assert "internal_code" in text
        assert "position_barcode" in text
        assert "product_label_quantity" in text
        assert "product_label_bbox" in text
        assert "source_image_id" in text
        assert "Do not omit canonical keys" in text


def test_openai_sdk_adapter_maps_schema_invalid() -> None:
    adapter = OpenAiSdkAdapter()
    settings = _settings_openai()
    bad = '{"total_entities_detected": 1, "entities": [{"entity_type": "INVALID"}]}'
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content=bad))]
    mock_completion.usage = None

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["f0"],
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


def test_openai_sdk_adapter_maps_rate_limit() -> None:
    from openai import RateLimitError

    adapter = OpenAiSdkAdapter()
    settings = _settings_openai()
    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["f0"],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )

    with patch("src.llm.openai_sdk_adapter.OpenAI") as client_cls:
        client_inst = MagicMock()
        client_inst.chat.completions.create.side_effect = RateLimitError(
            "rl", response=MagicMock(), body=None
        )
        client_cls.return_value = client_inst
        with pytest.raises(LLMProviderError) as ei:
            adapter.execute(req, settings)
        assert ei.value.code == "RATE_LIMIT"


def test_openai_sdk_adapter_maps_invalid_json() -> None:
    adapter = OpenAiSdkAdapter()
    settings = _settings_openai()
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="not json at all"))]
    mock_completion.usage = None

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["f0"],
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
        assert ei.value.code == "INVALID_JSON"


def test_openai_sdk_adapter_rejects_json_array_root() -> None:
    """B2.5: valid JSON but non-object root must map to INVALID_JSON (pipeline expects dict)."""
    adapter = OpenAiSdkAdapter()
    settings = _settings_openai()
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="[]"))]
    mock_completion.usage = None

    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["f0"],
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
        assert ei.value.code == "INVALID_JSON"


def test_extract_json_text_strips_markdown_fence() -> None:
    raw = '```json\n{"total_entities_detected": 0, "entities": []}\n```'
    t = _extract_json_text(raw)
    assert '"entities"' in t
    assert not t.startswith("```")


def test_openai_provider_delegates_to_adapter() -> None:
    from src.llm.providers.openai_provider import OpenAIProvider

    settings = _settings_openai()
    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["f0"],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )
    ok_json = '{"total_entities_detected": 0, "entities": []}'
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content=ok_json))]
    mock_completion.usage = None

    with patch("src.llm.openai_sdk_adapter.OpenAI") as client_cls:
        client_inst = MagicMock()
        client_inst.chat.completions.create.return_value = mock_completion
        client_cls.return_value = client_inst
        out = OpenAIProvider(settings).analyze_global(req)
        assert out.provider == "openai"
