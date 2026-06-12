"""Test doubles for JobResultUnitOfWork (Phase 2 Part 2 corrections)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.ports.job_result_unit_of_work import (
    JobResultRepositories,
    JobResultUnitOfWork,
)
from src.infrastructure.persistence.memory_job_result_unit_of_work import (
    MemoryJobResultUnitOfWork,
)
from tests.support.worker_phase2.scope_store_doubles import (
    AfterDeleteHook,
    HookingJobResultScopeStore,
    SpyJobResultScopeStore,
)


@dataclass
class HookingMemoryJobResultUnitOfWork(MemoryJobResultUnitOfWork):
    after_delete_hook: AfterDeleteHook | None = field(default=None)

    def __enter__(self) -> HookingMemoryJobResultUnitOfWork:
        super().__enter__()
        inner = self._scope_store
        assert inner is not None
        self._scope_store = HookingJobResultScopeStore(
            inner, after_delete_hook=self.after_delete_hook
        )
        return self


class HookingMemoryJobResultUnitOfWorkFactory:
    def __init__(self, *, after_delete_hook: AfterDeleteHook | None = None) -> None:
        self._after_delete_hook = after_delete_hook

    def __call__(self, repositories: JobResultRepositories) -> JobResultUnitOfWork:
        from src.infrastructure.persistence.job_result_bundle_validation import (
            assert_memory_job_result_bundle,
        )

        assert_memory_job_result_bundle(repositories)
        return HookingMemoryJobResultUnitOfWork(
            repositories=repositories,
            after_delete_hook=self._after_delete_hook,
        )


class SpyScopeStoreUnitOfWorkFactory:
    """Wraps memory UoW and exposes a spy scope store for contract tests."""

    def __init__(self) -> None:
        self.spy: SpyJobResultScopeStore | None = None

    def __call__(self, repositories: JobResultRepositories) -> JobResultUnitOfWork:
        from src.infrastructure.persistence.job_result_bundle_validation import (
            assert_memory_job_result_bundle,
        )

        assert_memory_job_result_bundle(repositories)
        uow = _SpyScopeStoreMemoryUoW(repositories=repositories, factory=self)
        return uow


class _SpyScopeStoreMemoryUoW(MemoryJobResultUnitOfWork):
    def __init__(
        self,
        repositories: JobResultRepositories,
        factory: SpyScopeStoreUnitOfWorkFactory,
        stage_store=None,
    ) -> None:
        super().__init__(repositories=repositories, stage_store=stage_store)
        self.factory = factory

    def __enter__(self) -> _SpyScopeStoreMemoryUoW:
        super().__enter__()
        inner = self._scope_store
        assert inner is not None
        spy = SpyJobResultScopeStore(inner)
        self._scope_store = spy
        self.factory.spy = spy
        return self
