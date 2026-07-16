"""Transactional boundary for job-scoped result persistence (Phase 2 Part 2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.application.ports.finalization_evidence_writer import FinalizationEvidenceWriter
from src.application.ports.job_result_scope_store import JobResultScopeStore
from src.application.ports.repositories import (
    EvidenceRepository,
    FinalCountRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    ResultEvidenceRepository,
)


@dataclass(frozen=True)
class JobResultRepositories:
    """Shared repository bundle for one persistence transaction."""

    position_repo: PositionRepository
    product_record_repo: ProductRecordRepository
    evidence_repo: EvidenceRepository
    raw_label_repo: RawLabelRepository
    normalized_label_repo: NormalizedLabelRepository
    final_count_repo: FinalCountRepository
    result_evidence_repo: ResultEvidenceRepository


@runtime_checkable
class JobResultUnitOfWork(Protocol):
    """One logical transaction for delete-replace + recompute of a job scope."""

    @property
    def repositories(self) -> JobResultRepositories: ...

    @property
    def scope_store(self) -> JobResultScopeStore: ...

    @property
    def finalization_evidence(self) -> FinalizationEvidenceWriter | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def acquire_image_result_lock(self, *, job_id: str, source_asset_id: str) -> None: ...

    def __enter__(self) -> JobResultUnitOfWork: ...

    def __exit__(self, exc_type, exc, tb) -> None: ...


class JobResultUnitOfWorkFactory(Protocol):
    def __call__(self, repositories: JobResultRepositories) -> JobResultUnitOfWork: ...
