"""
Structured, low-volume logging for legacy Stage-8 SQL repositories.

Logger name ``dinamic.legacy_sql`` is stable for log routing / filtering in staging and prod.

Phase 12.5 — Operational signals
---------------------------------
* ``legacy_sql_access`` (existing): one INFO line per repository operation (``jobs``,
  ``pallet_results``, ``job_events``), including ``path_kind`` (typically ``legacy_jobs`` when
  called from ``src.jobs.*``).
* ``legacy_sql_repositories_materialized_once_per_process`` (new): emitted **once** when
  ``job_store._db_repos()`` successfully constructs SQL repository instances for this process.
  Count these in aggregate to confirm whether any runtime still arms the legacy bridge.

Compare volume of ``legacy_sql_access`` (table=jobs|pallet_results|job_events) against v3
``inventory_jobs`` application logs/metrics separately; this module does not log v3 SQL.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Mapping, Optional

_LOG = logging.getLogger("dinamic.legacy_sql")

_LEGACY_SQL_REPOS_MATERIALIZED = False
_LEGACY_SQL_BRIDGE_BYPASS_LOGGED = False

_SKIP_MODULE_PREFIXES: tuple[str, ...] = (
    "src.legacy.persistence_observability",
    "src.database.repository",
)


def _truncate(value: Any, max_len: int = 120) -> str:
    s = repr(value)
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def classify_stage8_access_path_kind(caller_module: Optional[str]) -> str:
    if not caller_module:
        return "unknown"
    if caller_module.startswith("src.jobs"):
        return "legacy_jobs"
    if caller_module.startswith("src.api."):
        return "v3_api"
    if caller_module.startswith("src.application."):
        return "v3_application"
    if caller_module.startswith("src.infrastructure."):
        return "v3_infrastructure"
    if caller_module.startswith("src.runtime."):
        return "v3_runtime"
    if caller_module.startswith("src.database."):
        return "database_pkg"
    if caller_module.startswith("tests.") or caller_module.startswith("pytest"):
        return "tests"
    return "other"


def _resolve_caller_module(max_frames: int = 16) -> tuple[Optional[str], Optional[str]]:
    """Return (caller_module, caller_function) for the first frame outside this helper/repo."""
    for frame_info in inspect.stack()[2 : 2 + max_frames]:
        mod = inspect.getmodule(frame_info.frame)
        name = mod.__name__ if mod is not None else None
        if name is None:
            continue
        if any(name == p or name.startswith(p + ".") for p in _SKIP_MODULE_PREFIXES):
            continue
        func = frame_info.function
        return name, func
    return None, None


def log_legacy_sql_repositories_materialized_once_per_process(*, source: str) -> None:
    """Emit a single INFO per process when legacy ``JobsRepository`` trio is first constructed.

    Low noise: does not fire on each SQL call (those use ``log_stage8_sql_access``).
    """
    global _LEGACY_SQL_REPOS_MATERIALIZED
    if _LEGACY_SQL_REPOS_MATERIALIZED:
        return
    _LEGACY_SQL_REPOS_MATERIALIZED = True
    _LOG.info(
        "legacy_sql_repositories_materialized_once_per_process source=%s "
        "tables=jobs,pallet_results,job_events bridge=job_store_sql",
        source,
    )


def reset_legacy_sql_repositories_materialization_flag() -> None:
    """Reset the once-per-process materialization flag (unit tests only)."""
    global _LEGACY_SQL_REPOS_MATERIALIZED
    _LEGACY_SQL_REPOS_MATERIALIZED = False


def log_legacy_sql_bridge_bypassed_once_per_process(*, reason: str) -> None:
    """Emit once per process when ``job_store._db_repos()`` skips SQL repos (Phase 14.1 bridge disable)."""
    global _LEGACY_SQL_BRIDGE_BYPASS_LOGGED
    if _LEGACY_SQL_BRIDGE_BYPASS_LOGGED:
        return
    _LEGACY_SQL_BRIDGE_BYPASS_LOGGED = True
    _LOG.info(
        "legacy_sql_bridge_bypassed_once_per_process phase=14.1 reason=%s",
        reason,
    )


def reset_legacy_sql_bridge_bypassed_flag_for_tests() -> None:
    """Reset bridge-bypass log flag (unit tests only)."""
    global _LEGACY_SQL_BRIDGE_BYPASS_LOGGED
    _LEGACY_SQL_BRIDGE_BYPASS_LOGGED = False


def log_legacy_sql_write_blocked(
    *,
    operation: str,
    table: str,
    identifiers: Optional[Mapping[str, Any]] = None,
) -> None:
    """Phase 14.1 — a mutating legacy SQL operation was skipped (writes-disabled flag)."""
    parts: list[str] = []
    if identifiers:
        for k, v in identifiers.items():
            if v is None:
                continue
            parts.append(f"{k}={_truncate(v)}")
    id_blob = " ".join(parts) if parts else "-"
    _LOG.info(
        "legacy_sql_write_blocked phase=14.1 operation=%s table=%s identifiers=%s",
        operation,
        table,
        id_blob,
    )


def log_stage8_sql_access(
    *,
    repository_class: str,
    operation: str,
    table: str,
    identifiers: Optional[Mapping[str, Any]] = None,
) -> None:
    """Emit one concise INFO line per legacy SQL operation (no secrets / no payloads)."""
    caller_mod, caller_fn = _resolve_caller_module()
    path_kind = classify_stage8_access_path_kind(caller_mod)
    parts: list[str] = []
    if identifiers:
        for k, v in identifiers.items():
            if v is None:
                continue
            parts.append(f"{k}={_truncate(v)}")
    id_blob = " ".join(parts) if parts else "-"
    _LOG.info(
        "legacy_sql_access repository=%s operation=%s table=%s path_kind=%s caller_module=%s caller_function=%s identifiers=%s",
        repository_class,
        operation,
        table,
        path_kind,
        caller_mod or "-",
        caller_fn or "-",
        id_blob,
    )
