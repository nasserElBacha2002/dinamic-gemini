"""Repository persistence backend resolution (Phase C1 — foundation only).

Pure resolution logic lives here; :class:`~src.runtime.app_container.AppContainer` wires
settings, SQL probe, and env-driven fallback policy without importing concrete repositories.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from src.config import AppSettings


class RepositoryBackendMode(str, Enum):
    """How v3 repositories should use SQL Server vs in-process memory stores."""

    MEMORY_ONLY = "memory_only"
    SQL = "sql"
    MEMORY_FALLBACK = "memory_fallback"


@dataclass(frozen=True)
class RepositoryBackendResolution:
    """Outcome of a one-time (per process/container) repository backend decision."""

    mode: RepositoryBackendMode
    sql_enabled: bool
    fallback_allowed: bool
    reason: str | None = None


def _sql_persistence_target_enabled(settings: AppSettings) -> bool:
    """True when settings intend SQL as the persistence target (same gate as legacy ``_v3_db_enabled``)."""
    return bool(
        getattr(settings, "sqlserver_enabled", False)
        and (settings.sqlserver_effective_connection_string or "").strip()
    )


def resolve_repository_backend_mode(
    *,
    settings: AppSettings,
    probe_sql: Callable[[], None],
    allow_in_memory_fallback: Callable[[], bool],
) -> RepositoryBackendResolution:
    """
    Decide repository backend mode without instantiating repositories.

    - If SQL is not targeted by settings → :attr:`RepositoryBackendMode.MEMORY_ONLY` (no probe).
    - If SQL is targeted → ``probe_sql()``; on success → :attr:`RepositoryBackendMode.SQL`.
    - On probe failure → :attr:`RepositoryBackendMode.MEMORY_FALLBACK` if fallback allowed,
      else re-raises the original exception.

    ``probe_sql`` must perform connectivity validation (e.g. ``SELECT 1``) and may cache a client
    in the caller; it must not import infrastructure repository implementations.
    """
    fallback_allowed = allow_in_memory_fallback()
    sql_target = _sql_persistence_target_enabled(settings)
    if not sql_target:
        return RepositoryBackendResolution(
            mode=RepositoryBackendMode.MEMORY_ONLY,
            sql_enabled=False,
            fallback_allowed=fallback_allowed,
            reason="sqlserver_disabled_or_missing_effective_connection_string",
        )
    try:
        probe_sql()
    except Exception as exc:
        summary = f"{type(exc).__name__}: {exc}"
        if len(summary) > 500:
            summary = summary[:497] + "..."
        if fallback_allowed:
            return RepositoryBackendResolution(
                mode=RepositoryBackendMode.MEMORY_FALLBACK,
                sql_enabled=True,
                fallback_allowed=True,
                reason=summary,
            )
        raise
    return RepositoryBackendResolution(
        mode=RepositoryBackendMode.SQL,
        sql_enabled=True,
        fallback_allowed=fallback_allowed,
        reason=None,
    )
