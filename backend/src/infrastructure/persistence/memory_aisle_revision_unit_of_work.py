"""In-memory Unit of Work with snapshot rollback for aisle revision apply.

Rollback deep-copies every dict/list attribute of the wrapped memory repositories on enter and
restores them in place on rollback. This is best-effort by design (it cannot undo writes made
through repositories not listed in ``AisleRevisionRepositories``) and exists so unit tests can
assert atomicity without a SQL Server instance.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from src.application.ports.aisle_revision_unit_of_work import AisleRevisionRepositories

logger = logging.getLogger(__name__)


def _snapshot_repo(repo: Any) -> dict[str, Any]:
    """Deep-copy the mutable collections a memory repository keeps its rows in."""
    snapshot: dict[str, Any] = {}
    for name, value in list(vars(repo).items()):
        if isinstance(value, (dict, list)):
            snapshot[name] = copy.deepcopy(value)
    return snapshot


def _restore_repo(repo: Any, snapshot: dict[str, Any] | None) -> None:
    if not snapshot:
        return
    for name, value in snapshot.items():
        current = getattr(repo, name, None)
        if isinstance(current, dict) and isinstance(value, dict):
            current.clear()
            current.update(value)
        elif isinstance(current, list) and isinstance(value, list):
            current.clear()
            current.extend(value)


@dataclass
class MemoryAisleRevisionUnitOfWork:
    repositories: AisleRevisionRepositories
    _snapshots: dict[str, dict[str, Any]] | None = field(default=None, init=False)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)
    timing_ms: dict[str, float] = field(default_factory=dict, init=False)

    def _tracked_repos(self) -> dict[str, Any]:
        repos = self.repositories
        return {
            "revision": repos.revision_repo,
            "authoritative": repos.authoritative_repo,
            "position": repos.position_repo,
            "finalization": repos.finalization_repo,
        }

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")
        self._committed = True
        self._snapshots = None
        logger.debug("MemoryAisleRevisionUnitOfWork committed")

    def rollback(self) -> None:
        if self._rolled_back:
            return
        if self._snapshots is not None:
            for key, repo in self._tracked_repos().items():
                _restore_repo(repo, self._snapshots.get(key))
        self._committed = False
        self._rolled_back = True
        logger.warning("MemoryAisleRevisionUnitOfWork rolled back")

    def __enter__(self) -> MemoryAisleRevisionUnitOfWork:
        self._snapshots = {
            key: _snapshot_repo(repo) for key, repo in self._tracked_repos().items()
        }
        self._committed = False
        self._rolled_back = False
        self.timing_ms = {}
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if not self._committed:
                self.rollback()
        finally:
            self._snapshots = None


def build_memory_aisle_revision_uow_factory(
    repositories: AisleRevisionRepositories,
) -> Callable[[], MemoryAisleRevisionUnitOfWork]:
    def factory() -> MemoryAisleRevisionUnitOfWork:
        return MemoryAisleRevisionUnitOfWork(repositories=repositories)

    return factory
