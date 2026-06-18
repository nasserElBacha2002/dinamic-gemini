"""Shared PersistAisleResultUseCase builders for tests."""

from __future__ import annotations

from src.application.ports.clock import Clock
from src.application.ports.hybrid_report_to_domain_mapper import HybridReportToDomainMapper
from src.application.ports.job_result_unit_of_work import JobResultUnitOfWorkFactory
from src.application.ports.job_scoped_recompute import JobScopedRecomputeFactory
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    FinalCountRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    ResultEvidenceRepository,
)
from src.application.services.default_job_scoped_recompute_factory import (
    DefaultJobScopedRecomputeFactory,
)
from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultUseCase
from src.infrastructure.persistence.memory_job_result_unit_of_work import (
    MemoryJobResultUnitOfWorkFactory,
)
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)


def build_persist_aisle_result_use_case(
    *,
    position_repo: PositionRepository,
    product_record_repo: ProductRecordRepository,
    evidence_repo: EvidenceRepository,
    result_evidence_repo: ResultEvidenceRepository | None = None,
    aisle_repo: AisleRepository,
    raw_label_repo: RawLabelRepository,
    normalized_label_repo: NormalizedLabelRepository,
    final_count_repo: FinalCountRepository,
    clock: Clock,
    hybrid_mapper: HybridReportToDomainMapper | None = None,
    job_scoped_recompute_factory: JobScopedRecomputeFactory | None = None,
    job_result_uow_factory: JobResultUnitOfWorkFactory | None = None,
) -> PersistAisleResultUseCase:
    return PersistAisleResultUseCase(
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        evidence_repo=evidence_repo,
        result_evidence_repo=result_evidence_repo or MemoryResultEvidenceRepository(),
        clock=clock,
        hybrid_mapper=hybrid_mapper or default_map_hybrid_report_to_domain,
        aisle_repo=aisle_repo,
        raw_label_repo=raw_label_repo,
        normalized_label_repo=normalized_label_repo,
        final_count_repo=final_count_repo,
        job_scoped_recompute_factory=job_scoped_recompute_factory
        or DefaultJobScopedRecomputeFactory(),
        job_result_uow_factory=job_result_uow_factory or MemoryJobResultUnitOfWorkFactory(),
    )
