"""Shared helpers for set-based / batch SQL via pyodbc (no Stored Procedures).

Terminology (do not conflate):
- ``parameter_sets`` / ``executemany_calls``: Python/driver API invocations.
- SQL statement text executions: may still be expanded by the ODBC driver.
- Network RPCs / round trips: only claim when measured at the wire/driver layer.
- ``duration_ms``: wall-clock for the helper call (includes driver work).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Sequence
from typing import TypeVar

from src.application.ports.sql_cursor import SqlCursorLike

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Chunk sizes — two different constraints
# ---------------------------------------------------------------------------
#
# 1) Multi-parameter *single statement* (IN lists, VALUES tables):
#    SQL Server practical limit is ~2100 parameters per statement.
SQL_IN_CHUNK_SIZE = 400  # 1 placeholder per id → 400 params
SQL_VALUES_PAIR_CHUNK_SIZE = 200  # (?, ?) → 400 params
#
# 2) ``executemany`` parameter-*set* chunks:
#    Each execution reuses the *same* statement (fixed placeholder count).
#    Chunk size is about driver memory / binding behaviour, NOT 25×N < 2100.
#    Defaults chosen for moderate memory; refine via SQL integration benchmarks.
EXECUTEMANY_PRODUCTIVE_PARAM_SET_CHUNK = 80
EXECUTEMANY_IMPORT_ROW_PARAM_SET_CHUNK = 70

# Backward-compatible aliases used by existing call sites.
PRODUCTIVE_INSERT_CHUNK_SIZE = EXECUTEMANY_PRODUCTIVE_PARAM_SET_CHUNK
IMPORT_ROW_UPDATE_CHUNK_SIZE = EXECUTEMANY_IMPORT_ROW_PARAM_SET_CHUNK


def chunked(items: Sequence[T], size: int) -> Iterable[Sequence[T]]:
    if size < 1:
        raise ValueError("chunk size must be >= 1")
    for i in range(0, len(items), size):
        yield items[i : i + size]


def cursor_executemany(
    cur: SqlCursorLike,
    sql: str,
    seq_of_params: Sequence[Sequence[object]],
    *,
    operation: str,
    use_fast_executemany: bool = False,
) -> None:
    """Bind many parameter sets via ``executemany`` (or execute-loop fallback).

    This reduces *Python cursor API calls*. It does **not** by itself prove a
    matching reduction in ODBC network RPCs unless ``fast_executemany`` (or
    another measured batching mechanism) is validated for the driver in use.

    ``fast_executemany`` is opt-in and must be covered by SQL tests for NULL,
    datetime, and transaction/rollback behaviour before enabling on a path.
    """
    if not seq_of_params:
        return
    started = time.perf_counter()
    executemany = getattr(cur, "executemany", None)
    parameter_sets = len(seq_of_params)

    if not callable(executemany):
        for params in seq_of_params:
            cur.execute(sql, tuple(params))
        duration_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "sql_batch operation=%s parameter_sets=%s executemany_calls=%s "
            "mode=execute_loop fast_executemany=false duration_ms=%.2f",
            operation,
            parameter_sets,
            0,
            duration_ms,
        )
        return

    prev_fast: bool | None = None
    had_fast = hasattr(cur, "fast_executemany")
    try:
        if use_fast_executemany and had_fast:
            prev_fast = bool(getattr(cur, "fast_executemany"))
            setattr(cur, "fast_executemany", True)
        executemany(sql, seq_of_params)
    finally:
        if use_fast_executemany and had_fast and prev_fast is not None:
            setattr(cur, "fast_executemany", prev_fast)

    duration_ms = (time.perf_counter() - started) * 1000.0
    logger.info(
        "sql_batch operation=%s parameter_sets=%s executemany_calls=%s "
        "mode=executemany fast_executemany=%s duration_ms=%.2f",
        operation,
        parameter_sets,
        1,
        use_fast_executemany,
        duration_ms,
    )
