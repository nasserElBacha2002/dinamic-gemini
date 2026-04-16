"""Provider registry and canonical pipeline resolution exports (Phase 8).

``resolve_llm_executor_for_context`` is implemented in
:mod:`src.pipeline.services.pipeline_provider_resolver` and re-exported here for a stable
``src.pipeline.providers`` package surface. Adapter lookup remains on
:mod:`src.pipeline.providers.registry`.
"""

from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.providers.registry import (
    UnknownPipelineProviderError,
    default_analysis_provider,
    resolve_llm_executor,
)
from src.pipeline.services.pipeline_provider_resolver import resolve_llm_executor_for_context

__all__ = [
    "UnknownPipelineProviderError",
    "default_analysis_provider",
    "normalize_pipeline_provider_key",
    "resolve_llm_executor",
    "resolve_llm_executor_for_context",
]
