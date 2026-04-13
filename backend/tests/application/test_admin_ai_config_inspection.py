"""Admin AI config payload builder — no FastAPI app import (Python 3.9-safe unit tests)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.application.services.admin_ai_config_inspection import build_admin_ai_config_payload


def test_build_admin_ai_config_stable_shape_and_no_secret_attrs() -> None:
    s = MagicMock()
    s.llm_provider = "gemini"
    s.hybrid_prompt = "global_v21"
    s.prompt_version = ""
    s.gemini_api_key = "SECRET_GEMINI_SHOULD_NOT_APPEAR"
    s.openai_api_key = ""
    s.anthropic_api_key = ""
    s.deepseek_api_key = ""
    s.processing_gemini_models = "gemini-2.0-flash-exp"
    s.gemini_model_name = "gemini-2.0-flash-exp"
    s.processing_openai_models = "gpt-4o"
    s.openai_model = "gpt-4o"
    s.processing_claude_models = "claude-sonnet-4-20250514"
    s.anthropic_model = "claude-sonnet-4-20250514"
    s.processing_deepseek_models = "deepseek-chat"
    s.deepseek_model = "deepseek-chat"

    payload = build_admin_ai_config_payload(s)
    blob = str(payload).lower()
    assert "secret_gemini" not in blob
    # Credential *values* must not appear (descriptions may mention env names in prose).
    assert "secret_gemini_should_not_appear" not in blob
    assert len(payload["providers"]) == 4
    assert payload["server_defaults"]["llm_provider"] == "gemini"
    assert "prompt_variants" not in payload
    gemini = next(p for p in payload["providers"] if p["key"] == "gemini")
    assert isinstance(gemini["prompt_variants"], list)
    assert len(gemini["prompt_variants"]) >= 1
    assert "response_contract" in gemini
    assert gemini["response_contract"]["expects_json"] is True
    assert "total_entities_detected" in gemini["response_contract"]["canonical_example_json"]
    assert "overview" in gemini
    assert gemini["overview"]["credential_configured"] in (True, False)
    assert isinstance(gemini["composition_notes"]["bullets"], list)
