"""Execution spies for worker Phase 1 cancellation and finalization tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.infrastructure.pipeline.v3_job_executor import V3JobExecutor


@dataclass
class ExecutionSpy:
    """Counts invocations of executor collaborators."""

    pipeline_calls: int = 0
    persist_calls: int = 0
    recompute_calls: int = 0
    artifact_put_calls: int = 0
    mark_success_calls: int = 0
    fail_job_and_aisle_calls: int = 0
    cancel_job_calls: int = 0
    cancel_job_and_aisle_calls: int = 0

    _original_persist: Any = field(default=None, repr=False)
    _original_mark_success: Any = field(default=None, repr=False)
    _original_fail_job_and_aisle: Any = field(default=None, repr=False)
    _original_cancel_job: Any = field(default=None, repr=False)
    _original_cancel_job_and_aisle: Any = field(default=None, repr=False)
    _artifact_store: Any = field(default=None, repr=False)
    _original_put_object: Any = field(default=None, repr=False)

    def attach(self, executor: V3JobExecutor, *, artifact_store: Any | None = None) -> None:
        """Wrap executor collaborators; call ``detach`` in test teardown if not using fixture."""
        self._original_persist = executor._persist_use_case.execute

        def persist_spy(cmd: Any) -> None:
            self.persist_calls += 1
            self._original_persist(cmd)

        executor._persist_use_case.execute = persist_spy  # type: ignore[method-assign]

        recompute = getattr(executor._persist_use_case, "_recompute_uc", None)
        if recompute is not None:
            original_recompute = recompute.execute

            def recompute_spy(cmd: Any) -> Any:
                self.recompute_calls += 1
                return original_recompute(cmd)

            recompute.execute = recompute_spy  # type: ignore[method-assign]

        self._original_mark_success = executor._state.mark_success

        def mark_success_spy(*args: Any, **kwargs: Any) -> None:
            self.mark_success_calls += 1
            self._original_mark_success(*args, **kwargs)

        executor._state.mark_success = mark_success_spy  # type: ignore[method-assign]

        self._original_fail_job_and_aisle = executor._state.fail_job_and_aisle

        def fail_spy(*args: Any, **kwargs: Any) -> None:
            self.fail_job_and_aisle_calls += 1
            self._original_fail_job_and_aisle(*args, **kwargs)

        executor._state.fail_job_and_aisle = fail_spy  # type: ignore[method-assign]

        self._original_cancel_job = executor._state.cancel_job

        def cancel_job_spy(*args: Any, **kwargs: Any) -> None:
            self.cancel_job_calls += 1
            self._original_cancel_job(*args, **kwargs)

        executor._state.cancel_job = cancel_job_spy  # type: ignore[method-assign]

        self._original_cancel_job_and_aisle = executor._state.cancel_job_and_aisle

        def cancel_job_and_aisle_spy(*args: Any, **kwargs: Any) -> None:
            self.cancel_job_and_aisle_calls += 1
            self._original_cancel_job_and_aisle(*args, **kwargs)

        executor._state.cancel_job_and_aisle = cancel_job_and_aisle_spy  # type: ignore[method-assign]

        if artifact_store is not None:
            self._artifact_store = artifact_store
            self._original_put_object = artifact_store.put_object

            def put_spy(path: str, file_obj: Any, content_type: str) -> Any:
                self.artifact_put_calls += 1
                return self._original_put_object(path, file_obj, content_type)

            artifact_store.put_object = put_spy  # type: ignore[method-assign]

    def record_pipeline_call(self) -> None:
        self.pipeline_calls += 1

    def detach(self, executor: V3JobExecutor) -> None:
        if self._original_persist is not None:
            executor._persist_use_case.execute = self._original_persist  # type: ignore[method-assign]
        if self._original_mark_success is not None:
            executor._state.mark_success = self._original_mark_success  # type: ignore[method-assign]
        if self._original_fail_job_and_aisle is not None:
            executor._state.fail_job_and_aisle = self._original_fail_job_and_aisle  # type: ignore[method-assign]
        if self._original_cancel_job is not None:
            executor._state.cancel_job = self._original_cancel_job  # type: ignore[method-assign]
        if self._original_cancel_job_and_aisle is not None:
            executor._state.cancel_job_and_aisle = self._original_cancel_job_and_aisle  # type: ignore[method-assign]
        if self._artifact_store is not None and self._original_put_object is not None:
            self._artifact_store.put_object = self._original_put_object  # type: ignore[method-assign]
