"""Transactional finalization evidence writer bound to job-result UoW — Phase 3.3."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from src.domain.jobs.finalization_evidence import EvidenceLevel, FinalizationStage


@runtime_checkable
class FinalizationEvidenceWriter(Protocol):
    """Writes stage evidence in the same transaction as domain persistence."""

    def mark_stage_completed(
        self,
        *,
        job_id: str,
        stage: FinalizationStage,
        evidence_level: EvidenceLevel,
        completed_at: datetime,
        verification_source: str | None = None,
    ) -> None: ...
