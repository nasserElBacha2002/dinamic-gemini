"""Admin AI config payload builder — no FastAPI app import (Python 3.9-safe unit tests)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.application.services.admin_ai_config_inspection import (
    build_admin_ai_config_payload,
    compose_prompt_variant_for_inspection,
)


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
    assert "secret_gemini_should_not_appear" not in blob
    assert len(payload["providers"]) == 4
    assert payload["server_defaults"]["llm_provider"] == "gemini"
    assert "composed_prompt_text" not in blob
    gemini = next(p for p in payload["providers"] if p["key"] == "gemini")
    assert isinstance(gemini["prompt_variant_summaries"], list)
    assert len(gemini["prompt_variant_summaries"]) >= 1
    for row in gemini["prompt_variant_summaries"]:
        assert set(row.keys()) == {
            "prompt_key",
            "pipeline_provider_key",
            "prompt_parity_mode",
            "variant_label",
        }
    assert "response_contract" in gemini
    assert gemini["response_contract"]["expects_json"] is True
    assert "total_entities_detected" in gemini["response_contract"]["canonical_example_json"]
    assert "capabilities" in gemini
    assert "credential_configured" in gemini["capabilities"]
    assert "operationally_available" not in gemini["capabilities"]
    assert isinstance(gemini["composition"]["hybrid_base_mode"], str)


def test_compose_prompt_variant_rejects_invalid_combinations() -> None:
    assert (
        compose_prompt_variant_for_inspection(
            prompt_key="global_v21",
            pipeline_provider_key="claude",
            prompt_parity_mode=True,
        )
        is None
    )
    assert (
        compose_prompt_variant_for_inspection(
            prompt_key="nonexistent_profile_xyz",
            pipeline_provider_key="gemini",
            prompt_parity_mode=False,
        )
        is None
    )


def test_build_payload_empty_prompt_catalog() -> None:
    s = MagicMock()
    s.llm_provider = "gemini"
    s.hybrid_prompt = "global_v21"
    s.prompt_version = ""
    s.gemini_api_key = ""
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

    with patch(
        "src.application.services.admin_ai_config_inspection.prompt_profile_catalog",
        return_value=[],
    ):
        payload = build_admin_ai_config_payload(s)
    assert payload["prompt_catalog"] == []


def test_build_payload_empty_provider_registry() -> None:
    s = MagicMock()
    s.llm_provider = "gemini"
    s.hybrid_prompt = "global_v21"
    s.prompt_version = ""
    s.gemini_api_key = ""
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

    with patch(
        "src.application.services.admin_ai_config_inspection.PIPELINE_PROVIDER_SPECS", tuple()
    ):
        payload = build_admin_ai_config_payload(s)
    assert payload["providers"] == []


def test_build_payload_provider_with_no_models() -> None:
    s = MagicMock()
    s.llm_provider = "gemini"
    s.hybrid_prompt = "global_v21"
    s.prompt_version = ""
    s.gemini_api_key = ""
    s.openai_api_key = ""
    s.anthropic_api_key = ""
    s.deepseek_api_key = ""
    s.processing_gemini_models = ""
    s.gemini_model_name = ""
    s.processing_openai_models = "gpt-4o"
    s.openai_model = "gpt-4o"
    s.processing_claude_models = "claude-sonnet-4-20250514"
    s.anthropic_model = "claude-sonnet-4-20250514"
    s.processing_deepseek_models = "deepseek-chat"
    s.deepseek_model = "deepseek-chat"

    with (
        patch(
            "src.application.services.admin_ai_config_inspection.models_for_provider",
            return_value=[],
        ),
        patch(
            "src.application.services.admin_ai_config_inspection.default_model_for_provider",
            return_value=None,
        ),
    ):
        payload = build_admin_ai_config_payload(s)
    gemini = next(p for p in payload["providers"] if p["key"] == "gemini")
    assert gemini["models"] == []
    assert gemini["default_model"] is None
