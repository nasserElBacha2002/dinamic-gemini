from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from openai.types.chat import ChatCompletion
from openai.types.completion_usage import CompletionTokensDetails, CompletionUsage, PromptTokensDetails

from src.llm.openai_sdk_adapter import _openai_completion_usage_dict


def test_openai_completion_usage_dict_matches_active_sdk_shape() -> None:
    usage = CompletionUsage(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        prompt_tokens_details=PromptTokensDetails(cached_tokens=20),
        completion_tokens_details=CompletionTokensDetails(reasoning_tokens=10),
    )
    completion = ChatCompletion(
        id="chatcmpl-test",
        choices=[],
        created=0,
        model="gpt-4o",
        object="chat.completion",
        usage=usage,
    )
    d = _openai_completion_usage_dict(completion)
    assert d["prompt_tokens"] == 100
    assert d["completion_tokens"] == 50
    assert d["total_tokens"] == 150
    assert d["prompt_tokens_details"]["cached_tokens"] == 20
    assert d["completion_tokens_details"]["reasoning_tokens"] == 10


def test_openai_completion_usage_dict_empty_when_no_usage() -> None:
    completion = SimpleNamespace(usage=None)
    assert _openai_completion_usage_dict(completion) == {}


def test_openai_completion_usage_nested_model_dump_non_dict_omitted() -> None:
    """B2.5: if nested model_dump is not a dict, omit that key (avoid non-JSON usage blobs)."""
    nested = MagicMock()
    nested.model_dump = MagicMock(return_value=[])
    u = SimpleNamespace(
        model_dump=None,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        prompt_tokens_details=nested,
        completion_tokens_details=None,
    )
    completion = SimpleNamespace(usage=u)
    d = _openai_completion_usage_dict(completion)
    assert d["prompt_tokens"] == 10
    assert "prompt_tokens_details" not in d
