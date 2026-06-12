"""Transaction-bound recompute for one job scope during persist (Phase 2 Part 2)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.application.ports.job_result_unit_of_work import JobResultRepositories
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsResult,
)


@runtime_checkable
class JobScopedRecompute(Protocol):
    def execute(
        self, command: RecomputeConsolidatedCountsCommand
    ) -> RecomputeConsolidatedCountsResult: ...


@runtime_checkable
class JobScopedRecomputeFactory(Protocol):
    def create(self, repositories: JobResultRepositories) -> JobScopedRecompute: ...
