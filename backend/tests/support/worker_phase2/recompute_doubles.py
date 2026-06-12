"""Test doubles for job-scoped recompute factory (Phase 2 Part 2 corrections)."""

from __future__ import annotations

from src.application.ports.job_result_unit_of_work import JobResultRepositories
from src.application.ports.job_scoped_recompute import JobScopedRecompute, JobScopedRecomputeFactory
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsResult,
)


class FailingJobScopedRecomputeFactory(JobScopedRecomputeFactory):
    """Factory that always returns a recompute implementation that raises."""

    def __init__(self) -> None:
        self.execute_calls = 0
        self.last_repositories: JobResultRepositories | None = None
        self.last_command: RecomputeConsolidatedCountsCommand | None = None

    def create(self, repositories: JobResultRepositories) -> JobScopedRecompute:
        factory = self

        class _FailingRecompute:
            def execute(
                self, command: RecomputeConsolidatedCountsCommand
            ) -> RecomputeConsolidatedCountsResult:
                factory.execute_calls += 1
                factory.last_repositories = repositories
                factory.last_command = command
                raise RuntimeError("simulated recompute failure")

        return _FailingRecompute()


class SpyJobScopedRecomputeFactory(JobScopedRecomputeFactory):
    """Records factory invocations and delegates to an inner factory."""

    def __init__(self, inner: JobScopedRecomputeFactory) -> None:
        self.inner = inner
        self.create_calls = 0
        self.last_repositories: JobResultRepositories | None = None

    def create(self, repositories: JobResultRepositories) -> JobScopedRecompute:
        self.create_calls += 1
        self.last_repositories = repositories
        return self.inner.create(repositories)
