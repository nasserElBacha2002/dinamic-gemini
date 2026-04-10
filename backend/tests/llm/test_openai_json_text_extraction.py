"""Phase 2 — real-world-ish raw LLM text handling (markdown fences) for OpenAI adapter."""

from __future__ import annotations

import json

import pytest

from src.llm.openai_sdk_adapter import _extract_json_text


def test_extract_json_plain_object_unchanged() -> None:
    raw = '{"total_entities_detected": 1, "entities": []}'
    assert _extract_json_text(raw) == raw


def test_extract_json_strips_json_markdown_fence() -> None:
    inner = {"total_entities_detected": 0, "entities": []}
    raw = "```json\n" + json.dumps(inner) + "\n```"
    assert _extract_json_text(raw) == json.dumps(inner)


def test_extract_json_strips_fence_without_language_tag() -> None:
    raw = "```\n{}\n```"
    assert _extract_json_text(raw) == "{}"


def test_extract_json_strips_leading_trailing_whitespace() -> None:
    assert _extract_json_text('  \n{"a":1}\n  ') == '{"a":1}'


def test_extract_json_stripped_content_may_still_be_invalid_json() -> None:
    """Fence stripping does not validate JSON — callers must handle ``json.loads`` failures."""
    stripped = _extract_json_text("```\n{not json\n```")
    assert stripped == "{not json"
    with pytest.raises(json.JSONDecodeError):
        json.loads(stripped)
