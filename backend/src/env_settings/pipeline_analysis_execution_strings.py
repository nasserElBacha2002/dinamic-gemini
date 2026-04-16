"""
Phase 4 — string validation for hybrid multi-provider execution settings.

Lives under ``env_settings`` so :mod:`src.env_settings.grouped_settings` can validate fields
without importing the pipeline package (avoids circular imports via ``src.config`` → jobs).
"""

from __future__ import annotations

from typing import Optional

STRATEGY_SINGLE = "single"
STRATEGY_MULTI_PARALLEL = "multi_parallel"
STRATEGY_MULTI_SEQUENTIAL = "multi_sequential"

_VALID_STRATEGIES_AFTER_NORMALIZE = frozenset(
    {STRATEGY_SINGLE, STRATEGY_MULTI_PARALLEL, STRATEGY_MULTI_SEQUENTIAL}
)


def normalize_pipeline_analysis_strategy_value(raw: Optional[str]) -> str:
    """
    Normalize user/job strategy labels.

    ``multi_fallback`` is an alias for ``multi_sequential``.

    **Naming note:** ``STRATEGY_MULTI_SEQUENTIAL`` means **sequential fallback** (try providers in
    order until one succeeds). It does **not** mean “run every provider in sequence and keep all
    results” for comparison; that would be a different strategy.
    """
    s = (raw or STRATEGY_SINGLE).strip().lower()
    if s in ("multi_fallback",):
        return STRATEGY_MULTI_SEQUENTIAL
    return s


def validate_pipeline_analysis_strategy_for_settings(value: str) -> str:
    """Pydantic ``field_validator`` helper: reject unknown labels after normalization."""
    normalized = normalize_pipeline_analysis_strategy_value(value)
    if normalized not in _VALID_STRATEGIES_AFTER_NORMALIZE:
        allowed = ", ".join(sorted(_VALID_STRATEGIES_AFTER_NORMALIZE | {"multi_fallback"}))
        raise ValueError(f"pipeline_analysis_execution_strategy must be one of: {allowed}")
    return normalized
