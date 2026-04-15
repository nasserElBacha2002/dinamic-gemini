from __future__ import annotations

from types import SimpleNamespace

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
