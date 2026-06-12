"""In-memory finalization stage store with optimistic concurrency — Phase 3.3."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from src.application.ports.finalization_stage_store import FinalizationStageConcurrencyError
from src.application.services.finalization_stage_transitions import assert_stage_transition_allowed
from src.domain.jobs.finalization_evidence import (
    EvidenceLevel,
    FinalizationStage,
    FinalizationStageRecord,
    StageStatus,
)


def _key(job_id: str, stage: FinalizationStage) -> tuple[str, str]:
    return job_id, stage.value


class MemoryFinalizationStageStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], FinalizationStageRecord] = {}

    def snapshot(self) -> dict[tuple[str, str], FinalizationStageRecord]:
        return copy.deepcopy(self._rows)

    def restore(self, snapshot: dict[tuple[str, str], FinalizationStageRecord]) -> None:
        self._rows = copy.deepcopy(snapshot)

    def get_stage(
        self, job_id: str, stage: FinalizationStage
    ) -> FinalizationStageRecord | None:
        row = self._rows.get(_key(job_id, stage))
        return copy.deepcopy(row) if row is not None else None

    def list_stages(self, job_id: str) -> Sequence[FinalizationStageRecord]:
        rows = [copy.deepcopy(r) for r in self._rows.values() if r.job_id == job_id]
        rows.sort(key=lambda r: r.stage.value)
        return rows

    def upsert_stage(
        self,
        record: FinalizationStageRecord,
        *,
        expected_version: int | None = None,
    ) -> FinalizationStageRecord:
        k = _key(record.job_id, record.stage)
        existing = self._rows.get(k)
        if expected_version is not None:
            if existing is None or existing.version != expected_version:
                raise FinalizationStageConcurrencyError(
                    f"Stage version conflict job_id={record.job_id} stage={record.stage.value}"
                )
        if existing is not None:
            assert_stage_transition_allowed(existing.status, record.status)
        stored = copy.deepcopy(record)
        self._rows[k] = stored
        return copy.deepcopy(stored)

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
    ) -> FinalizationStageRecord:
        existing = self._rows.get(_key(job_id, stage))
        if expected_version is not None:
            if existing is None or existing.version != expected_version:
                raise FinalizationStageConcurrencyError(
                    f"Stage version conflict job_id={job_id} stage={stage.value}"
                )
        current_status = existing.status if existing else StageStatus.NOT_STARTED
        assert_stage_transition_allowed(current_status, new_status)
        version = 1 if existing is None else existing.version + 1
        attempt = 1 if existing is None else existing.attempt_count + (
            1 if new_status in (StageStatus.IN_PROGRESS, StageStatus.FAILED) else 0
        )
        record = FinalizationStageRecord(
            job_id=job_id,
            stage=stage,
            status=new_status,
            evidence_level=evidence_level,
            completed_at=completed_at,
            verified_at=verified_at,
            verification_source=verification_source,
            attempt_count=attempt,
            last_error_code=last_error_code,
            last_error_metadata=last_error_metadata,
            version=version,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._rows[_key(job_id, stage)] = copy.deepcopy(record)
        return copy.deepcopy(record)
