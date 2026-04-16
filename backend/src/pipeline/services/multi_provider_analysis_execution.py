"""
Phase 4 — multi-provider analysis execution (parallel, sequential / fallback).

Invoked from :class:`~src.pipeline.adapters.hybrid_global_analysis_strategy.HybridGlobalAnalysisStrategy`
after prompt/visual-reference preparation is unchanged; each branch calls the same ``analyze_once``
with a ``RunContext`` whose ``pipeline_provider_name`` is set for that logical provider.

Default single-provider runs do not enter this module (fast path preserves Phase 1–3 behavior).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Callable, Dict, List, Optional, Sequence

from src.llm.errors import LLMProviderError
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import AnalysisResult
from src.pipeline.services.provider_analysis_execution_config import (
    STRATEGY_MULTI_PARALLEL,
    STRATEGY_MULTI_SEQUENTIAL,
)
from src.pipeline.services.provider_result_aggregator import (
    attach_multi_provider_trace,
    model_label_from_analysis_result,
    select_primary_first_in_order,
)

logger = logging.getLogger(__name__)


def _short_exc_message(exc: BaseException, limit: int = 240) -> str:
    msg = str(exc).strip()
    if len(msg) > limit:
        return msg[: limit - 3] + "..."
    return msg


def _run_row_ok(provider_key: str, result: AnalysisResult) -> Dict[str, Any]:
    return {
        "provider_key": provider_key,
        "status": "ok",
        "provider_name": result.provider_name,
        "model": model_label_from_analysis_result(result),
    }


def _run_row_error(provider_key: str, exc: BaseException) -> Dict[str, Any]:
    if isinstance(exc, LLMProviderError):
        return {
            "provider_key": provider_key,
            "status": "error",
            "error_class": "LLMProviderError",
            "error_code": getattr(exc, "code", None),
            "message": _short_exc_message(exc),
        }
    return {
        "provider_key": provider_key,
        "status": "error",
        "error_class": type(exc).__name__,
        "error_code": None,
        "message": _short_exc_message(exc),
    }


def dispatch_multi_provider_analysis(
    *,
    strategy_name: str,
    base_context: RunContext,
    ordered_provider_keys: Sequence[str],
    analyze_once: Callable[[RunContext], AnalysisResult],
    run_logger: Optional[logging.Logger],
) -> AnalysisResult:
    """
    Run two or more providers and return a single primary ``AnalysisResult``.

    ``analyze_once`` must perform one full hybrid analysis call for the given context
    (including executor resolution via Phase 3).
    """
    keys = list(ordered_provider_keys)
    if len(keys) < 2:
        return analyze_once(base_context)

    base_context.emit_stage_event(
        stage="AnalysisStage",
        event="multi_provider_execution_started",
        details={
            "strategy": strategy_name,
            "ordered_provider_keys": keys,
        },
    )

    if strategy_name == STRATEGY_MULTI_PARALLEL:
        return _execute_parallel(
            base_context=base_context,
            keys=keys,
            analyze_once=analyze_once,
            run_logger=run_logger,
        )
    if strategy_name == STRATEGY_MULTI_SEQUENTIAL:
        return _execute_sequential_fallback(
            base_context=base_context,
            keys=keys,
            analyze_once=analyze_once,
            run_logger=run_logger,
        )
    raise ValueError(f"Unsupported multi-provider strategy: {strategy_name!r}")


def _execute_parallel(
    *,
    base_context: RunContext,
    keys: List[str],
    analyze_once: Callable[[RunContext], AnalysisResult],
    run_logger: Optional[logging.Logger],
) -> AnalysisResult:
    results_by_key: Dict[str, AnalysisResult] = {}

    with ThreadPoolExecutor(max_workers=len(keys)) as pool:
        future_to_key = {
            pool.submit(analyze_once, replace(base_context, pipeline_provider_name=k)): k for k in keys
        }
        for fut, k in future_to_key.items():
            results_by_key[k] = fut.result()

    ordered_results = [results_by_key[k] for k in keys]
    primary = select_primary_first_in_order(ordered_results)
    trace: Dict[str, Any] = {
        "strategy_effective": STRATEGY_MULTI_PARALLEL,
        "ordered_provider_keys": keys,
        "primary_provider_key": keys[0],
        "runs": [_run_row_ok(k, results_by_key[k]) for k in keys],
    }
    if run_logger is not None:
        run_logger.info(
            "Multi-provider parallel analysis completed primary=%s also_ran=%s",
            keys[0],
            keys[1:],
        )
    return attach_multi_provider_trace(primary, trace=trace)


def _execute_sequential_fallback(
    *,
    base_context: RunContext,
    keys: List[str],
    analyze_once: Callable[[RunContext], AnalysisResult],
    run_logger: Optional[logging.Logger],
) -> AnalysisResult:
    runs: List[Dict[str, Any]] = []
    last_exc: Optional[BaseException] = None
    for idx, k in enumerate(keys):
        ctx = replace(base_context, pipeline_provider_name=k)
        try:
            result = analyze_once(ctx)
            runs.append(_run_row_ok(k, result))
            for k2 in keys[idx + 1 :]:
                runs.append(
                    {
                        "provider_key": k2,
                        "status": "skipped",
                        "reason": "prior_provider_succeeded",
                    }
                )
            trace: Dict[str, Any] = {
                "strategy_effective": STRATEGY_MULTI_SEQUENTIAL,
                "ordered_provider_keys": keys,
                "primary_provider_key": k,
                "runs": runs,
            }
            if run_logger is not None:
                run_logger.info(
                    "Multi-provider sequential analysis succeeded primary=%s attempted=%s",
                    k,
                    keys[: idx + 1],
                )
            return attach_multi_provider_trace(result, trace=trace)
        except LLMProviderError as e:
            last_exc = e
            runs.append(_run_row_error(k, e))
            if run_logger is not None:
                run_logger.warning(
                    "Multi-provider sequential attempt failed provider=%s code=%s",
                    k,
                    getattr(e, "code", None),
                )

    assert last_exc is not None
    base_context.emit_stage_event(
        stage="AnalysisStage",
        event="multi_provider_execution_failed",
        details={"ordered_provider_keys": keys, "last_error": _short_exc_message(last_exc)},
        level="error",
    )
    raise last_exc
