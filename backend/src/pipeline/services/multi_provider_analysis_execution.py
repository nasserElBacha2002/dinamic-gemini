"""
Phase 4 / 6 / 7 — multi-provider analysis execution (parallel, sequential fallback).

**Coordinator role:** this module runs ``analyze_once`` per provider key and attaches execution
trace metadata to the primary ``AnalysisResult``. It does **not** build prompts or resolve
executors — that stays in :class:`~src.pipeline.adapters.hybrid_global_analysis_strategy.HybridGlobalAnalysisStrategy`.

Invoked from ``HybridGlobalAnalysisStrategy`` after prompt/visual-reference preparation is unchanged;
each branch calls the same ``analyze_once`` with a ``RunContext`` whose ``pipeline_provider_name``
is set for that logical provider.

**``multi_parallel`` error policy:** every provider in ``ordered_provider_keys`` must complete
successfully. Work is submitted concurrently; results are awaited in **key list order**, and the
first ``Future.result()`` in that sequence that raises propagates and fails the whole run. There is
no partial-success merge of parsed outputs in this phase.

**``multi_sequential``:** tries keys in order and returns on the first success (fallback). It does
*not* run every provider for side-by-side comparison; see ``_execute_sequential_fallback``.

Default single-provider runs do not enter this module (fast path preserves Phase 1–3 behavior).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from typing import Callable

from src.llm.errors import LLMProviderError
from src.pipeline.context.run_context import RunContext
from src.pipeline.contracts.multi_provider_trace_types import (
    MultiProviderExecutionTrace,
    MultiProviderRunRow,
    MultiProviderRunRowError,
    MultiProviderRunRowOk,
    MultiProviderRunRowSkipped,
)
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


def _run_row_ok(provider_key: str, result: AnalysisResult) -> MultiProviderRunRowOk:
    return {
        "provider_key": provider_key,
        "status": "ok",
        "provider_name": result.provider_name,
        "model": model_label_from_analysis_result(result),
    }


def _run_row_error(provider_key: str, exc: BaseException) -> MultiProviderRunRowError:
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


def _sequential_skipped_trace_entries(
    keys: list[str], successful_index: int
) -> list[MultiProviderRunRowSkipped]:
    """Trace rows for providers not attempted after a sequential fallback success at ``successful_index``."""
    return [
        {"provider_key": k2, "status": "skipped", "reason": "prior_provider_succeeded"}
        for k2 in keys[successful_index + 1 :]
    ]


def _parallel_trace_payload(
    *,
    keys: list[str],
    results_by_key: dict[str, AnalysisResult],
) -> MultiProviderExecutionTrace:
    """Assemble the ``multi_provider_execution`` trace for a successful parallel run."""
    runs: list[MultiProviderRunRow] = [_run_row_ok(k, results_by_key[k]) for k in keys]
    return {
        "strategy_effective": STRATEGY_MULTI_PARALLEL,
        "ordered_provider_keys": keys,
        "primary_provider_key": keys[0],
        "runs": runs,
    }


def _sequential_success_trace_payload(
    *,
    keys: list[str],
    successful_key: str,
    runs: list[MultiProviderRunRow],
) -> MultiProviderExecutionTrace:
    """Assemble the ``multi_provider_execution`` trace after sequential fallback succeeds."""
    return {
        "strategy_effective": STRATEGY_MULTI_SEQUENTIAL,
        "ordered_provider_keys": keys,
        "primary_provider_key": successful_key,
        "runs": runs,
    }


def _collect_parallel_results_by_key(
    *,
    base_context: RunContext,
    keys: list[str],
    analyze_once: Callable[[RunContext], AnalysisResult],
) -> dict[str, AnalysisResult]:
    """Submit one ``analyze_once`` per key, then await each future in **key order** (all-or-nothing)."""
    results_by_key: dict[str, AnalysisResult] = {}
    with ThreadPoolExecutor(max_workers=len(keys)) as pool:
        futures_by_key: dict[str, Future[AnalysisResult]] = {
            k: pool.submit(analyze_once, replace(base_context, pipeline_provider_name=k))
            for k in keys
        }
        for k in keys:
            results_by_key[k] = futures_by_key[k].result()
    return results_by_key


def dispatch_multi_provider_analysis(
    *,
    strategy_name: str,
    base_context: RunContext,
    ordered_provider_keys: Sequence[str],
    analyze_once: Callable[[RunContext], AnalysisResult],
    run_logger: logging.Logger | None,
) -> AnalysisResult:
    """
    Run two or more providers and return a single primary ``AnalysisResult``.

    ``analyze_once`` must perform one full hybrid analysis call for the given context
    (including executor resolution via Phase 3).

    For ``multi_parallel``, the primary result is the outcome for ``ordered_provider_keys[0]``
    once *all* branches succeed (see module docstring). Selection is order-based, not quality-based.
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
    keys: list[str],
    analyze_once: Callable[[RunContext], AnalysisResult],
    run_logger: logging.Logger | None,
) -> AnalysisResult:
    """
    Run all keys concurrently; **all** must succeed or this function raises.

    Results are collected by iterating ``keys`` in order so ``Future.result()`` ordering is explicit
    (first failure in that order propagates; semantics match “all-or-nothing”, not best-of).
    """
    results_by_key = _collect_parallel_results_by_key(
        base_context=base_context,
        keys=keys,
        analyze_once=analyze_once,
    )
    ordered_results = [results_by_key[k] for k in keys]
    primary = select_primary_first_in_order(ordered_results)
    trace = _parallel_trace_payload(keys=keys, results_by_key=results_by_key)
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
    keys: list[str],
    analyze_once: Callable[[RunContext], AnalysisResult],
    run_logger: logging.Logger | None,
) -> AnalysisResult:
    """
    Sequential **fallback**: try ``keys[0]``, then ``keys[1]``, … until one ``analyze_once`` succeeds.

    On first success, remaining keys are recorded as ``skipped`` in the trace (they are not invoked
    for comparison). Only :class:`~src.llm.errors.LLMProviderError` is caught between attempts; other
    exceptions propagate immediately.

    This is intentionally **not** “run every provider sequentially and collect all results” (that would
    be a different strategy for a later phase).
    """
    runs: list[MultiProviderRunRow] = []
    last_exc: BaseException | None = None
    for idx, k in enumerate(keys):
        ctx = replace(base_context, pipeline_provider_name=k)
        try:
            result = analyze_once(ctx)
            runs.append(_run_row_ok(k, result))
            runs.extend(_sequential_skipped_trace_entries(keys, idx))
            trace = _sequential_success_trace_payload(keys=keys, successful_key=k, runs=runs)
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
