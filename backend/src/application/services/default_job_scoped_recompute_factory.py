"""Production factory for transaction-bound job-scoped recompute."""

from __future__ import annotations

from src.application.ports.job_result_unit_of_work import JobResultRepositories
from src.application.ports.job_scoped_recompute import JobScopedRecompute, JobScopedRecomputeFactory
from src.application.services.final_count_builder import FinalCountBuilder
from src.application.services.label_normalization import LabelNormalizationService
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.labels.merge import MergeRuleEngine


class DefaultJobScopedRecomputeFactory(JobScopedRecomputeFactory):
    def __init__(
        self,
        *,
        normalization_service: LabelNormalizationService | None = None,
        final_count_builder: FinalCountBuilder | None = None,
    ) -> None:
        self._normalization = normalization_service or LabelNormalizationService(
            merge_rule_engine=MergeRuleEngine()
        )
        self._builder = final_count_builder or FinalCountBuilder()

    def create(self, repositories: JobResultRepositories) -> JobScopedRecompute:
        return RecomputeConsolidatedCountsUseCase(
            raw_label_repo=repositories.raw_label_repo,
            normalized_label_repo=repositories.normalized_label_repo,
            final_count_repo=repositories.final_count_repo,
            product_record_repo=repositories.product_record_repo,
            position_repo=repositories.position_repo,
            normalization_service=self._normalization,
            final_count_builder=self._builder,
        )
