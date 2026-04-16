"""
Structured, low-volume logging for legacy Stage-8 SQL repositories.

Logger name ``dinamic.legacy_sql`` is stable for log routing / filtering in staging and prod.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Mapping, Optional

_LOG = logging.getLogger("dinamic.legacy_sql")

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
