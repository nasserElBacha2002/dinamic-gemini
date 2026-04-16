"""Provider registry and resolution (Phase 4).

``resolve_llm_executor_for_context`` is re-exported from :mod:`src.pipeline.providers.registry` as a
compatibility shim; new code should prefer :mod:`src.pipeline.services.pipeline_provider_resolver`.
"""

from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.providers.registry import (
    UnknownPipelineProviderError,
    default_analysis_provider,
    resolve_llm_executor,
    resolve_llm_executor_for_context,
)

__all__ = [
    "UnknownPipelineProviderError",
    "default_analysis_provider",
    "normalize_pipeline_provider_key",
    "resolve_llm_executor",
    "resolve_llm_executor_for_context",
]
