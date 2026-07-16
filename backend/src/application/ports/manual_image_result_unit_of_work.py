"""Unit of Work for atomic manual image-result creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.ports.job_image_coverage_repository import JobImageCoverageRepository
from src.application.ports.manual_image_coverage_repository import ManualImageCoverageRepository
from src.application.ports.repositories import (
    EvidenceRepository,
    PositionRepository,
    ProductRecordRepository,
    ResultEvidenceRepository,
    ReviewActionRepository,
)


@dataclass
class ManualImageResultRepositories:
    position_repo: PositionRepository
    product_record_repo: ProductRecordRepository
    evidence_repo: EvidenceRepository
    manual_coverage_repo: ManualImageCoverageRepository
    result_evidence_repo: ResultEvidenceRepository
    review_repo: ReviewActionRepository
    image_coverage_repo: JobImageCoverageRepository


class ManualImageResultUnitOfWork(Protocol):
    repositories: ManualImageResultRepositories
    timing_ms: dict[str, float]

    def bind_lifecycle_scope(self, *, inventory_id: str, aisle_id: str) -> None: ...

    def acquire_image_result_lock(self, *, job_id: str, source_asset_id: str) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> ManualImageResultUnitOfWork: ...

    def __exit__(self, exc_type, exc, tb) -> None: ...
