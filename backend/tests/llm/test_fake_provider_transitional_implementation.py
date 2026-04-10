"""
Transitional production tests for ``FakeProvider`` (Phase 3 will remove the provider).

These are **not** pipeline integration tests: they only assert the in-repo implementation
until ``fake`` is deleted from the registry and codebase.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.llm.providers.fake_provider import DEFAULT_FAKE_RESPONSE, FakeProvider
from src.llm.types import LLMRequest


def test_fake_provider_returns_v21_shaped_json() -> None:
    settings = MagicMock()
    settings.fake_llm_fixture_path = None
    provider = FakeProvider(settings)
    request = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="",
        schema_version="v2.1",
        metadata={},
    )
    response = provider.analyze_global(request)
    assert response.provider == "fake"
    assert "total_entities_detected" in response.parsed_json
    assert "entities" in response.parsed_json
    assert isinstance(response.parsed_json["entities"], list)
    assert response.parsed_json["total_entities_detected"] == len(response.parsed_json["entities"])


def test_fake_provider_uses_fixture_path_when_set(tmp_path: Path) -> None:
    fixture = {"total_entities_detected": 1, "entities": [{"model_entity_id": "e1", "entity_type": "PALLET"}]}
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    settings = MagicMock()
    settings.fake_llm_fixture_path = str(path)
    provider = FakeProvider(settings)
    request = LLMRequest(job_id="j1", frames=[], frame_refs=[], prompt="", schema_version="v2.1", metadata={})
    response = provider.analyze_global(request)
    assert response.parsed_json["total_entities_detected"] == 1
    assert len(response.parsed_json["entities"]) == 1
    assert response.parsed_json["entities"][0]["model_entity_id"] == "e1"


def test_fake_provider_default_fixture_is_minimal() -> None:
    assert DEFAULT_FAKE_RESPONSE["total_entities_detected"] == 0
    assert DEFAULT_FAKE_RESPONSE["entities"] == []
