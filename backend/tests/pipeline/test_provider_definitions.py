"""Central provider definitions stay aligned with registry and public API keys."""

from __future__ import annotations

import pytest

from src.pipeline.providers.definitions import (
    PIPELINE_PROVIDER_SPECS,
    registered_pipeline_provider_keys_from_definitions,
)
from src.pipeline.providers.registry import registered_pipeline_provider_keys


def test_definition_keys_match_registry() -> None:
    """Registry ``_KNOWN_KEYS`` is derived from ``PIPELINE_PROVIDER_SPECS`` — catch drift early."""
    keys = registered_pipeline_provider_keys_from_definitions()
    assert keys == registered_pipeline_provider_keys()
    assert keys == frozenset(s.key for s in PIPELINE_PROVIDER_SPECS)


def test_specs_have_distinct_keys() -> None:
    ks = [s.key for s in PIPELINE_PROVIDER_SPECS]
    assert len(ks) == len(set(ks))
