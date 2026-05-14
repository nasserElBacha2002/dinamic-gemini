"""Application use-case construction not covered by prompt-config builders (Phase C4)."""

from __future__ import annotations

from src.application.ports.repositories import (
    FinalCountRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsUseCase,
)


def build_recompute_consolidated_counts_use_case(
    *,
    raw_label_repo: RawLabelRepository,
    normalized_label_repo: NormalizedLabelRepository,
    final_count_repo: FinalCountRepository,
    product_record_repo: ProductRecordRepository,
    position_repo: PositionRepository,
) -> RecomputeConsolidatedCountsUseCase:
    from src.application.services.final_count_builder import FinalCountBuilder
    from src.application.services.label_normalization import LabelNormalizationService
    from src.domain.labels.merge import MergeRuleEngine

    return RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw_label_repo,
        normalized_label_repo=normalized_label_repo,
        final_count_repo=final_count_repo,
        product_record_repo=product_record_repo,
        position_repo=position_repo,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )
