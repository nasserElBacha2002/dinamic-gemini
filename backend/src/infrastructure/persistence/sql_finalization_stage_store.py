"""SQL Server finalization stage store — Phase 3.3."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.ports.finalization_stage_store import FinalizationStageConcurrencyError
from src.application.services.finalization_stage_transitions import assert_stage_transition_allowed
from src.database.sqlserver import SqlServerClient
from src.domain.jobs.finalization_evidence import (
    EvidenceLevel,
    FinalizationStage,
    FinalizationStageRecord,
    StageStatus,
)
from src.infrastructure.database.sql_transaction import sql_repository_cursor

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _parse_json(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    text = raw.strip() if isinstance(raw, str) else str(raw).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _row_to_record(row: Any) -> FinalizationStageRecord:
    return FinalizationStageRecord(
        job_id=str(row.job_id),
        stage=FinalizationStage(str(row.stage)),
        status=StageStatus(str(row.status)),
        evidence_level=EvidenceLevel(str(row.evidence_level)),
        completed_at=_ensure_utc(getattr(row, "completed_at", None)),
        verified_at=_ensure_utc(getattr(row, "verified_at", None)),
        verification_source=getattr(row, "verification_source", None),
        attempt_count=int(getattr(row, "attempt_count", 0) or 0),
        last_error_code=getattr(row, "last_error_code", None),
        last_error_metadata=_parse_json(getattr(row, "last_error_metadata", None)),
        version=int(getattr(row, "version", 1) or 1),
        created_at=_ensure_utc(getattr(row, "created_at", None)),
        updated_at=_ensure_utc(getattr(row, "updated_at", None)),
    )


class SqlFinalizationStageStore:
    def __init__(self, client: SqlServerClient, *, connection: Any | None = None) -> None:
        self._client = client
        self._connection = connection

    def get_stage(
        self, job_id: str, stage: FinalizationStage
    ) -> FinalizationStageRecord | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT job_id, stage, status, evidence_level, completed_at, verified_at,
                       verification_source, attempt_count, last_error_code,
                       last_error_metadata, version, created_at, updated_at
                FROM job_finalization_stages
                WHERE job_id = ? AND stage = ?
                """,
                (job_id, stage.value),
            )
            row = cur.fetchone()
            return _row_to_record(row) if row is not None else None

    def list_stages(self, job_id: str) -> Sequence[FinalizationStageRecord]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT job_id, stage, status, evidence_level, completed_at, verified_at,
                       verification_source, attempt_count, last_error_code,
                       last_error_metadata, version, created_at, updated_at
                FROM job_finalization_stages
                WHERE job_id = ?
                ORDER BY stage
                """,
                (job_id,),
            )
            return [_row_to_record(row) for row in cur.fetchall()]

    def upsert_stage(
        self,
        record: FinalizationStageRecord,
        *,
        expected_version: int | None = None,
    ) -> FinalizationStageRecord:
        return self.transition_stage(
            job_id=record.job_id,
            stage=record.stage,
            new_status=record.status,
            evidence_level=record.evidence_level,
            completed_at=record.completed_at,
            verified_at=record.verified_at,
            verification_source=record.verification_source,
            last_error_code=record.last_error_code,
            last_error_metadata=record.last_error_metadata,
            expected_version=expected_version,
            now=record.updated_at or datetime.now(timezone.utc),
        )

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
        existing = self.get_stage(job_id, stage)
        if existing is None:
            if expected_version is not None:
                raise FinalizationStageConcurrencyError(
                    f"Stage create conflict job_id={job_id} stage={stage.value}"
                )
        elif expected_version is None or existing.version != expected_version:
            raise FinalizationStageConcurrencyError(
                f"Stage version conflict job_id={job_id} stage={stage.value}"
            )
        current_status = existing.status if existing else StageStatus.NOT_STARTED
        assert_stage_transition_allowed(current_status, new_status)
        version = 1 if existing is None else existing.version + 1
        attempt = 1 if existing is None else existing.attempt_count + (
            1 if new_status in (StageStatus.IN_PROGRESS, StageStatus.FAILED) else 0
        )
        metadata_json = (
            json.dumps(last_error_metadata, ensure_ascii=False, default=str)
            if last_error_metadata
            else None
        )
        created_at = existing.created_at if existing and existing.created_at else now
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO job_finalization_stages (
                        job_id, stage, status, evidence_level, completed_at, verified_at,
                        verification_source, attempt_count, last_error_code,
                        last_error_metadata, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        stage.value,
                        new_status.value,
                        evidence_level.value,
                        completed_at,
                        verified_at,
                        verification_source,
                        attempt,
                        last_error_code,
                        metadata_json,
                        version,
                        created_at,
                        now,
                    ),
                )
            else:
                if expected_version is not None:
                    cur.execute(
                        """
                        UPDATE job_finalization_stages
                        SET status = ?, evidence_level = ?, completed_at = ?, verified_at = ?,
                            verification_source = ?, attempt_count = ?, last_error_code = ?,
                            last_error_metadata = ?, version = ?, updated_at = ?
                        WHERE job_id = ? AND stage = ? AND version = ?
                        """,
                        (
                            new_status.value,
                            evidence_level.value,
                            completed_at,
                            verified_at,
                            verification_source,
                            attempt,
                            last_error_code,
                            metadata_json,
                            version,
                            now,
                            job_id,
                            stage.value,
                            expected_version,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE job_finalization_stages
                        SET status = ?, evidence_level = ?, completed_at = ?, verified_at = ?,
                            verification_source = ?, attempt_count = ?, last_error_code = ?,
                            last_error_metadata = ?, version = ?, updated_at = ?
                        WHERE job_id = ? AND stage = ?
                        """,
                        (
                            new_status.value,
                            evidence_level.value,
                            completed_at,
                            verified_at,
                            verification_source,
                            attempt,
                            last_error_code,
                            metadata_json,
                            version,
                            now,
                            job_id,
                            stage.value,
                        ),
                    )
                if expected_version is not None and cur.rowcount == 0:
                    raise FinalizationStageConcurrencyError(
                        f"Stage version conflict job_id={job_id} stage={stage.value}"
                    )
        stored = self.get_stage(job_id, stage)
        if stored is None:
            raise RuntimeError(f"Stage row missing after upsert job_id={job_id} stage={stage.value}")
        return stored
