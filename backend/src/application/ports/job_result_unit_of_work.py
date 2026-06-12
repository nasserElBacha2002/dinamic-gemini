"""Transactional boundary for job-scoped result persistence (Phase 2 Part 2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.application.ports.repositories import (
    EvidenceRepository,
    FinalCountRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
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


@runtime_checkable
class JobResultUnitOfWork(Protocol):
    """One logical transaction for delete-replace + recompute of a job scope."""

    @property
    def repositories(self) -> JobResultRepositories: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> JobResultUnitOfWork: ...

    def __exit__(self, exc_type, exc, tb) -> None: ...


class JobResultUnitOfWorkFactory(Protocol):
    def __call__(self, repositories: JobResultRepositories) -> JobResultUnitOfWork: ...
