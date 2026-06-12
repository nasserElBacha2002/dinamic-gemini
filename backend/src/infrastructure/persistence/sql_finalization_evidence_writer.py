"""Transactional finalization evidence writer for SQL UoW — Phase 3.3."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.domain.jobs.finalization_evidence import (
    EvidenceLevel,
    FinalizationStage,
    StageStatus,
)
from src.infrastructure.persistence.sql_finalization_stage_store import SqlFinalizationStageStore


class SqlFinalizationEvidenceWriter:
    """Buffered stage writes applied on UoW commit within the open SQL transaction."""

    def __init__(self, stage_store: SqlFinalizationStageStore) -> None:
        self._stage_store = stage_store
        self._buffer: list[tuple] = []

    def mark_stage_completed(
        self,
        *,
        job_id: str,
        stage: FinalizationStage,
        evidence_level: EvidenceLevel,
        completed_at: datetime,
        verification_source: str | None = None,
    ) -> None:
        self._buffer.append(
            (
                job_id,
                stage,
                StageStatus.COMPLETED,
                evidence_level,
                completed_at,
                verification_source,
            )
        )

    def flush(self, now: datetime | None = None) -> None:
        ts = now or datetime.now(timezone.utc)
        for job_id, stage, status, level, completed_at, source in self._buffer:
            self._stage_store.transition_stage(
                job_id=job_id,
                stage=stage,
                new_status=status,
                evidence_level=level,
                completed_at=completed_at,
                verified_at=completed_at if level == EvidenceLevel.TRANSACTIONAL else None,
                verification_source=source or "uow_commit",
                now=ts,
            )
        self._buffer.clear()

    def discard(self) -> None:
        self._buffer.clear()
