"""
Phase 7 — narrow settings surface for :mod:`src.pipeline.services.provider_analysis_execution_config`.

**Intentionally not** full :class:`~src.config.Settings`: helpers use ``getattr`` defensively for
tests and partial doubles; this :class:`typing.Protocol` documents the attributes that *must* be
readable when present so job + defaults resolution matches production ``AppSettings`` / grouped LLM
settings. Unknown attributes on duck-typed test objects are still handled at runtime (e.g.
``isinstance(..., str)`` guards).
"""

from __future__ import annotations

from typing import Protocol


class SupportsPipelineAnalysisExecutionSettings(Protocol):
    """Fields read when resolving multi-provider strategy and extra provider keys from settings."""

    llm_provider: str
    pipeline_analysis_execution_strategy: str
    pipeline_analysis_extra_provider_keys: str
