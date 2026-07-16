"""In-memory Unit of Work with snapshot rollback for manual image-result creation."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from src.application.ports.manual_image_result_unit_of_work import (
    ManualImageResultRepositories,
)
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync

logger = logging.getLogger(__name__)


def _storage_repo(repo: Any) -> Any | None:
    if getattr(repo, "_store", None) is not None:
        return repo
    inner = getattr(repo, "_inner", None)
    if inner is not None and getattr(inner, "_store", None) is not None:
        return inner
    return None


def _snapshot_store(repo: Any) -> dict[Any, Any] | list[Any] | None:
    storage = _storage_repo(repo)
    if storage is None:
        return None
    store = storage._store
    if isinstance(store, dict):
        return copy.deepcopy(store)
    if isinstance(store, list):
        return copy.deepcopy(store)
    return None


def _restore_store(repo: Any, snapshot: dict | list | None) -> None:
    if snapshot is None:
        return
    storage = _storage_repo(repo)
    if storage is None:
        return
    store = storage._store
    if isinstance(store, dict) and isinstance(snapshot, dict):
        store.clear()
        store.update(snapshot)
    elif isinstance(store, list) and isinstance(snapshot, list):
        store.clear()
        store.extend(snapshot)


def _snapshot_coverage(repo: Any) -> dict[tuple[str, str], Any] | None:
    by_key = getattr(repo, "_by_key", None)
    if by_key is None:
        return None
    return copy.deepcopy(by_key)


def _restore_coverage(repo: Any, snapshot: dict[tuple[str, str], Any] | None) -> None:
    if snapshot is None:
        return
    by_key = getattr(repo, "_by_key", None)
    by_id = getattr(repo, "_by_id", None)
    if by_key is None:
        return
    by_key.clear()
    by_key.update(snapshot)
    if by_id is not None:
        by_id.clear()
        for link in snapshot.values():
            by_id[link.id] = link


@dataclass
class MemoryManualImageResultUnitOfWork:
    repositories: ManualImageResultRepositories
    _lifecycle_sync: AisleReviewLifecycleSync
    _inventory_id: str | None = field(default=None, init=False)
    _aisle_id: str | None = field(default=None, init=False)
    _snapshots: dict[str, Any] | None = field(default=None, init=False)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)
    timing_ms: dict[str, float] = field(default_factory=dict, init=False)

    def bind_lifecycle_scope(self, *, inventory_id: str, aisle_id: str) -> None:
        self._inventory_id = inventory_id
        self._aisle_id = aisle_id

    def acquire_image_result_lock(self, *, job_id: str, source_asset_id: str) -> None:
        # Memory mode is single-process; lock is a no-op for unit tests.
        _ = (job_id, source_asset_id)
        self.timing_ms["lock_acquisition_ms"] = 0.0

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")
        if self._inventory_id and self._aisle_id:
            self._lifecycle_sync.after_review_mutation(self._inventory_id, self._aisle_id)
        self._committed = True
        self._snapshots = None
        logger.debug("MemoryManualImageResultUnitOfWork committed")

    def rollback(self) -> None:
        if self._rolled_back:
            return
        if self._snapshots is not None:
            repos = self.repositories
            _restore_store(repos.position_repo, self._snapshots.get("position"))
            _restore_store(repos.product_record_repo, self._snapshots.get("product"))
            _restore_store(repos.evidence_repo, self._snapshots.get("evidence"))
            _restore_store(repos.result_evidence_repo, self._snapshots.get("result_evidence"))
            _restore_store(repos.review_repo, self._snapshots.get("review"))
            _restore_coverage(repos.manual_coverage_repo, self._snapshots.get("coverage"))
        self._committed = False
        self._rolled_back = True
        logger.warning("MemoryManualImageResultUnitOfWork rolled back")

    def __enter__(self) -> MemoryManualImageResultUnitOfWork:
        repos = self.repositories
        self._snapshots = {
            "position": _snapshot_store(repos.position_repo),
            "product": _snapshot_store(repos.product_record_repo),
            "evidence": _snapshot_store(repos.evidence_repo),
            "result_evidence": _snapshot_store(repos.result_evidence_repo),
            "review": _snapshot_store(repos.review_repo),
            "coverage": _snapshot_coverage(repos.manual_coverage_repo),
        }
        self._committed = False
        self._rolled_back = False
        self.timing_ms = {}
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None and not self._committed:
                self.rollback()
            elif not self._committed and exc_type is None:
                self.rollback()
        finally:
            self._snapshots = None


def build_memory_manual_image_result_uow_factory(
    repositories: ManualImageResultRepositories,
    lifecycle_sync: AisleReviewLifecycleSync,
) -> Callable[[], MemoryManualImageResultUnitOfWork]:
    def factory() -> MemoryManualImageResultUnitOfWork:
        return MemoryManualImageResultUnitOfWork(
            repositories=repositories,
            _lifecycle_sync=lifecycle_sync,
        )

    return factory
