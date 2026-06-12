"""Port for authoritative finalization stage evidence — Phase 3.3."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from src.domain.jobs.finalization_evidence import (
    EvidenceLevel,
    FinalizationStage,
    FinalizationStageRecord,
    StageStatus,
)


class FinalizationStageConcurrencyError(Exception):
    """Optimistic concurrency conflict on stage update."""


@runtime_checkable
class FinalizationStageStore(Protocol):
    def get_stage(
        self, job_id: str, stage: FinalizationStage
    ) -> FinalizationStageRecord | None: ...

    def list_stages(self, job_id: str) -> Sequence[FinalizationStageRecord]: ...

    def upsert_stage(
        self,
        record: FinalizationStageRecord,
        *,
        expected_version: int | None = None,
    ) -> FinalizationStageRecord: ...

    def transition_stage(
        self,
        *,
        job_id: str,
        stage: FinalizationStage,
        new_status: StageStatus,
        evidence_level: EvidenceLevel,
        completed_at: datetime | None = None,
        verified_at: datetime | None = None,
        verification_source: str | None = None,
        last_error_code: str | None = None,
        last_error_metadata: dict[str, Any] | None = None,
        expected_version: int | None = None,
        now: datetime,
    ) -> FinalizationStageRecord: ...
