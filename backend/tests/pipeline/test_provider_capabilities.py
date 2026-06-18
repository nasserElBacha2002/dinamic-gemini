"""Phase 5 — provider capability contract."""

from __future__ import annotations

from src.pipeline.providers.capabilities import (
    CAPABILITIES_BY_PROVIDER_KEY,
    assert_capabilities_registered_for_all_provider_keys,
    provider_supports_visual_inventory,
)
from src.pipeline.providers.definitions import (
    PIPELINE_PROVIDER_SPECS,
    registered_pipeline_provider_keys_from_definitions,
)


def test_every_registered_provider_has_capability_spec() -> None:
    keys = registered_pipeline_provider_keys_from_definitions()
    assert_capabilities_registered_for_all_provider_keys(keys)
    assert keys == frozenset(CAPABILITIES_BY_PROVIDER_KEY.keys())


def test_spec_capabilities_property_matches_registry() -> None:
    for spec in PIPELINE_PROVIDER_SPECS:
        caps = spec.capabilities
        assert caps is not None
        assert caps is CAPABILITIES_BY_PROVIDER_KEY[spec.key]


def test_active_vision_providers_support_visual_inventory() -> None:
    for key in ("gemini", "openai", "claude"):
        assert provider_supports_visual_inventory(key)


def test_deepseek_does_not_support_visual_inventory() -> None:
    assert not provider_supports_visual_inventory("deepseek")
    caps = CAPABILITIES_BY_PROVIDER_KEY["deepseek"]
    assert caps.supports_vision is False
    assert caps.supports_image_binding is False


def test_unknown_provider_key_defers_visual_preflight() -> None:
    assert provider_supports_visual_inventory("test_llm_harness_provider")


def test_gemini_structured_output_declared() -> None:
    caps = CAPABILITIES_BY_PROVIDER_KEY["gemini"]
    assert caps.supports_structured_output is True
    assert caps.supports_json_mode is True


def test_claude_json_mode_conservative() -> None:
    caps = CAPABILITIES_BY_PROVIDER_KEY["claude"]
    assert caps.supports_vision is True
    assert caps.supports_structured_output is False
    assert caps.supports_json_mode is False
