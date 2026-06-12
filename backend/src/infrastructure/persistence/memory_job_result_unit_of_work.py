"""In-memory Unit of Work with snapshot rollback for job-result persistence."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from src.application.ports.job_result_scope_store import JobResultScopeStore
from src.application.ports.job_result_unit_of_work import (
    JobResultRepositories,
    JobResultUnitOfWork,
)
from src.infrastructure.persistence.job_result_bundle_validation import (
    assert_memory_job_result_bundle,
)
from src.infrastructure.persistence.memory_job_result_scope_store import (
    MemoryJobResultScopeStore,
)

logger = logging.getLogger(__name__)


def _storage_repo(repo: Any) -> Any | None:
    if getattr(repo, "_store", None) is not None:
        return repo
    inner = getattr(repo, "_inner", None)
    if inner is not None and getattr(inner, "_store", None) is not None:
        return inner
    return None


def _snapshot_store(repo: Any) -> dict | None:
    storage = _storage_repo(repo)
    if storage is None:
        return None
    return copy.deepcopy(storage._store)


def _restore_store(repo: Any, snapshot: dict | None) -> None:
    if snapshot is None:
        return
    storage = _storage_repo(repo)
    if storage is None:
        return
    storage._store.clear()
    storage._store.update(snapshot)


@dataclass
class MemoryJobResultUnitOfWork:
    repositories: JobResultRepositories
    _scope_store: JobResultScopeStore | None = field(default=None, init=False)
    _snapshots: dict[str, dict | None] | None = field(default=None, init=False)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)

    @property
    def scope_store(self) -> JobResultScopeStore:
        if self._scope_store is None:
            raise RuntimeError("MemoryJobResultUnitOfWork is not active")
        return self._scope_store

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")
        self._committed = True
        self._snapshots = None
        logger.debug("MemoryJobResultUnitOfWork committed")

    def rollback(self) -> None:
        if self._rolled_back:
            return
        if self._snapshots is None:
            self._rolled_back = True
            return
        repos = self.repositories
        _restore_store(repos.position_repo, self._snapshots.get("positions"))
        _restore_store(repos.product_record_repo, self._snapshots.get("products"))
        _restore_store(repos.evidence_repo, self._snapshots.get("evidence"))
        _restore_store(repos.raw_label_repo, self._snapshots.get("raw_labels"))
        _restore_store(repos.normalized_label_repo, self._snapshots.get("normalized_labels"))
        _restore_store(repos.final_count_repo, self._snapshots.get("final_counts"))
        self._snapshots = None
        self._rolled_back = True
        logger.warning("MemoryJobResultUnitOfWork rolled back to prior snapshot")

    def __enter__(self) -> MemoryJobResultUnitOfWork:
        repos = self.repositories
        self._scope_store = MemoryJobResultScopeStore(repos)
        self._snapshots = {
            "positions": _snapshot_store(repos.position_repo),
            "products": _snapshot_store(repos.product_record_repo),
            "evidence": _snapshot_store(repos.evidence_repo),
            "raw_labels": _snapshot_store(repos.raw_label_repo),
            "normalized_labels": _snapshot_store(repos.normalized_label_repo),
            "final_counts": _snapshot_store(repos.final_count_repo),
        }
        self._committed = False
        self._rolled_back = False
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None and not self._committed:
                self.rollback()
            elif not self._committed and exc_type is None:
                self.rollback()
        finally:
            self._scope_store = None


class MemoryJobResultUnitOfWorkFactory:
    def __call__(self, repositories: JobResultRepositories) -> JobResultUnitOfWork:
        assert_memory_job_result_bundle(repositories)
        return MemoryJobResultUnitOfWork(repositories=repositories)
