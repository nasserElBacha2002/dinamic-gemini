"""Central provider definitions stay aligned with registry and public API keys."""

from __future__ import annotations

from src.pipeline.providers.definitions import (
    PIPELINE_PROVIDER_SPECS,
    is_pipeline_provider_active,
    registered_active_pipeline_provider_keys_from_definitions,
    registered_pipeline_provider_keys_from_definitions,
)
from src.pipeline.providers.registry import (
    _EXECUTOR_BUILDERS,
    registered_pipeline_provider_keys,
)


def test_definition_keys_match_registry() -> None:
    """Registry ``_KNOWN_KEYS`` is derived from ``PIPELINE_PROVIDER_SPECS`` — catch drift early."""
    keys = registered_pipeline_provider_keys_from_definitions()
    assert keys == registered_pipeline_provider_keys()
    assert keys == frozenset(s.key for s in PIPELINE_PROVIDER_SPECS)
    assert frozenset(_EXECUTOR_BUILDERS) == keys


def test_specs_have_distinct_keys() -> None:
    ks = [s.key for s in PIPELINE_PROVIDER_SPECS]
    assert len(ks) == len(set(ks))


def test_deepseek_is_registered_but_inactive() -> None:
    assert "deepseek" in registered_pipeline_provider_keys_from_definitions()
    assert "deepseek" not in registered_active_pipeline_provider_keys_from_definitions()
    assert is_pipeline_provider_active("deepseek") is False
    assert is_pipeline_provider_active("gemini") is True
