"""Test doubles for JobResultScopeStore (Phase 2 Part 2 corrections)."""

from __future__ import annotations

from collections.abc import Callable

from src.application.ports.job_result_scope_store import JobResultScopeStore, JobScopeRowCounts

AfterDeleteHook = Callable[[], None]


class HookingJobResultScopeStore(JobResultScopeStore):
    def __init__(
        self,
        inner: JobResultScopeStore,
        *,
        after_delete_hook: AfterDeleteHook | None = None,
    ) -> None:
        self._inner = inner
        self._after_delete_hook = after_delete_hook
        self.delete_calls = 0
        self.count_calls = 0

    def count_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobScopeRowCounts:
        self.count_calls += 1
        return self._inner.count_scope(
            inventory_id=inventory_id, aisle_id=aisle_id, job_id=job_id
        )

    def delete_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobScopeRowCounts:
        self.delete_calls += 1
        result = self._inner.delete_scope(
            inventory_id=inventory_id, aisle_id=aisle_id, job_id=job_id
        )
        if self._after_delete_hook is not None:
            self._after_delete_hook()
        return result


class SpyJobResultScopeStore(JobResultScopeStore):
    def __init__(self, inner: JobResultScopeStore) -> None:
        self._inner = inner
        self.delete_calls = 0
        self.count_calls = 0

    def count_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobScopeRowCounts:
        self.count_calls += 1
        return self._inner.count_scope(
            inventory_id=inventory_id, aisle_id=aisle_id, job_id=job_id
        )

    def delete_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobScopeRowCounts:
        self.delete_calls += 1
        return self._inner.delete_scope(
            inventory_id=inventory_id, aisle_id=aisle_id, job_id=job_id
        )
