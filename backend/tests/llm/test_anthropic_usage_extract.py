from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from anthropic.types import Message, Usage

from src.llm.anthropic_sdk_adapter import _anthropic_message_usage_dict


def test_anthropic_message_usage_dict_matches_active_sdk_shape() -> None:
    usage = Usage(
        input_tokens=120,
        output_tokens=40,
        cache_read_input_tokens=30,
        cache_creation_input_tokens=10,
    )
    message = Message(
        id="msg_1",
        content=[],
        model="claude-sonnet-4-20250514",
        role="assistant",
        stop_reason="end_turn",
        type="message",
        usage=usage,
    )
    d = _anthropic_message_usage_dict(message)
    assert d["input_tokens"] == 120
    assert d["output_tokens"] == 40
    assert d["cache_read_input_tokens"] == 30
    assert d["cache_creation_input_tokens"] == 10


def test_anthropic_message_usage_dict_empty_when_no_usage() -> None:
    message = SimpleNamespace(usage=None)
    assert _anthropic_message_usage_dict(message) == {}


def test_anthropic_message_usage_nested_model_dump_non_dict_falls_back() -> None:
    """B2.5: nested usage fields with broken model_dump stay as raw objects."""
    nested = MagicMock()
    nested.model_dump = MagicMock(return_value="not-a-dict")
    u = SimpleNamespace(
        model_dump=None,
        input_tokens=12,
        output_tokens=7,
        cache_creation=nested,
    )
    message = SimpleNamespace(usage=u)
    d = _anthropic_message_usage_dict(message)
    assert d["input_tokens"] == 12
    assert d["cache_creation"] is nested
