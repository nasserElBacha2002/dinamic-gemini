"""
Phase 4 / 6 / 7 — explicit multi-provider analysis execution **configuration** (policy inputs only).

Resolves strategy name and ordered provider keys from ``RunContext`` (per-job) and
``LlmProviderSettings`` (defaults). Keeps Phase 3 resolution rules: primary key via
:class:`~src.pipeline.services.pipeline_provider_resolver.PipelineProviderResolver`.

**Does not execute** LLM calls or choose per-branch outcomes — that belongs in the hybrid strategy
and :mod:`src.pipeline.services.multi_provider_analysis_execution`.

**Strategy semantics (see also :mod:`src.env_settings.pipeline_analysis_execution_strings`):**

- ``single`` — one provider; extras are ignored by the hybrid strategy fast path.
- ``multi_parallel`` — all listed providers run concurrently; **all** must succeed.
- ``multi_sequential`` / ``multi_fallback`` — sequential **fallback** (first success wins), not
  full sequential multi-result comparison.
"""

from __future__ import annotations

import logging

from src.env_settings.pipeline_analysis_execution_strings import (
    STRATEGY_MULTI_PARALLEL,
    STRATEGY_MULTI_SEQUENTIAL,
    STRATEGY_SINGLE,
    normalize_pipeline_analysis_strategy_value,
)
from src.pipeline.context.run_context import RunContext
from src.pipeline.contracts.pipeline_analysis_execution_settings import (
    SupportsPipelineAnalysisExecutionSettings,
)
from src.pipeline.providers.registry import registered_pipeline_provider_keys
from src.pipeline.services.pipeline_provider_resolver import PipelineProviderResolver

logger = logging.getLogger(__name__)


def effective_analysis_execution_strategy(
    context: RunContext,
    settings: SupportsPipelineAnalysisExecutionSettings,
) -> str:
    """
    Effective strategy string after normalization (e.g. ``multi_fallback`` → ``multi_sequential``).

    Job ``RunContext.analysis_execution_strategy`` overrides settings when set to a non-empty string.
    """
    job = getattr(context, "analysis_execution_strategy", None)
    if isinstance(job, str) and job.strip():
        return normalize_pipeline_analysis_strategy_value(job)
    raw = getattr(settings, "pipeline_analysis_execution_strategy", STRATEGY_SINGLE)
    if not isinstance(raw, str):
        raw = STRATEGY_SINGLE
    return normalize_pipeline_analysis_strategy_value(raw)


def _parse_comma_separated_keys(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or "").split(","):
        k = (part or "").strip().lower()
        if k and k not in out:
            out.append(k)
    return out


def effective_extra_provider_keys(
    context: RunContext,
    settings: SupportsPipelineAnalysisExecutionSettings,
) -> list[str]:
    """
    Extra providers after the job/settings primary.

    ``RunContext.analysis_extra_provider_keys`` wins when not ``None`` (including empty tuple).
    """
    tup = getattr(context, "analysis_extra_provider_keys", None)
    if tup is not None:
        return [str(x).strip().lower() for x in tup if str(x).strip()]
    s = getattr(settings, "pipeline_analysis_extra_provider_keys", "")
    if not isinstance(s, str):
        s = ""
    return _parse_comma_separated_keys(s)


def build_ordered_provider_keys(
    context: RunContext,
    settings: SupportsPipelineAnalysisExecutionSettings,
) -> list[str]:
    """
    Return ``[primary, ...extras]`` with deduplication; extras must be registered pipeline keys.

    Unknown extra tokens are skipped with a warning (deterministic, no silent wrong-vendor runs).
    """
    primary = PipelineProviderResolver.effective_provider_key(context.pipeline_provider_name, settings)
    known = registered_pipeline_provider_keys()
    extras = effective_extra_provider_keys(context, settings)
    ordered_extras: list[str] = []
    for k in extras:
        if k == primary:
            continue
        if k not in known:
            logger.warning(
                "Ignoring unknown pipeline_analysis extra provider key %r (known=%s)",
                k,
                sorted(known),
            )
            continue
        if k not in ordered_extras:
            ordered_extras.append(k)
    return [primary] + ordered_extras
