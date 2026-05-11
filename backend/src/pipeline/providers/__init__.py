"""Provider registry and canonical pipeline resolution exports (Phase 8).

``resolve_llm_executor_for_context`` is implemented in
:mod:`src.pipeline.services.pipeline_provider_resolver` and re-exported here for a stable
``src.pipeline.providers`` package surface. Adapter lookup remains on
:mod:`src.pipeline.providers.registry`.

**Import note:** the resolver is loaded lazily via :func:`__getattr__` to avoid a circular import:
``pipeline_provider_resolver`` imports ``registry`` while ``registry`` is still being bound as a
submodule of this package, so an eager re-export of ``resolve_llm_executor_for_context`` here would
re-enter this ``__init__`` before ``registry`` finished loading.
"""

from __future__ import annotations

from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.providers.registry import (
    UnknownPipelineProviderError,
    default_analysis_provider,
    resolve_llm_executor,
)

__all__ = [
    "UnknownPipelineProviderError",
    "default_analysis_provider",
    "normalize_pipeline_provider_key",
    "resolve_llm_executor",
    "resolve_llm_executor_for_context",
]


def __getattr__(name: str):
    if name == "resolve_llm_executor_for_context":
        from src.pipeline.services.pipeline_provider_resolver import (
            resolve_llm_executor_for_context,
        )

        return resolve_llm_executor_for_context
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
