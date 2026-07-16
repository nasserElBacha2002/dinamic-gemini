"""Unit of Work for atomic manual image-result creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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


class ManualImageResultUnitOfWork(Protocol):
  repositories: ManualImageResultRepositories

  def commit(self) -> None: ...

  def rollback(self) -> None: ...

  def __enter__(self) -> ManualImageResultUnitOfWork: ...

  def __exit__(self, exc_type, exc, tb) -> None: ...
