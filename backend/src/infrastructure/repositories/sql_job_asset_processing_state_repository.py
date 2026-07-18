"""SQL Server JobAssetProcessingStateRepository (Phase 2)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.image_processing_repositories import (
    AssetProgressCounts,
    JobAssetProcessingStateRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _row_to_state(row: object) -> JobAssetProcessingState:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "PENDING"
    try:
        status = JobAssetProcessingStatus(status_raw)
    except ValueError:
        logger.error(
            "invalid_persisted_job_asset_status value=%s job_id=%s asset_id=%s",
            status_raw,
            getattr(row, "job_id", None),
            getattr(row, "asset_id", None),
        )
        raise
    return JobAssetProcessingState(
        id=str(getattr(row, "id")),
        job_id=str(getattr(row, "job_id")),
        asset_id=str(getattr(row, "asset_id")),
        status=status,
        active_result_id=normalize_db_str(getattr(row, "active_result_id", None)),
        attempt_count=int(getattr(row, "attempt_count", 0) or 0),
        last_strategy=normalize_db_str(getattr(row, "last_strategy", None)),
        started_at=_ensure_utc(getattr(row, "started_at", None)),
        finished_at=_ensure_utc(getattr(row, "finished_at", None)),
        duration_ms=getattr(row, "duration_ms", None),
        error_code=normalize_db_str(getattr(row, "error_code", None)),
        error_message=normalize_db_str(getattr(row, "error_message", None)),
        created_at=_ensure_utc(getattr(row, "created_at")) or datetime.now(timezone.utc),
        updated_at=_ensure_utc(getattr(row, "updated_at")) or datetime.now(timezone.utc),
        version=int(getattr(row, "version", 1) or 1),
        execution_scope=normalize_db_str(getattr(row, "execution_scope", None)),
    )


class SqlJobAssetProcessingStateRepository(JobAssetProcessingStateRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, state: JobAssetProcessingState) -> None:
        existing = self.get_by_job_and_asset(state.job_id, state.asset_id)
        if existing is None:
            self._client.execute(
                """
                INSERT INTO job_asset_processing_states (
                    id, job_id, asset_id, status, active_result_id, attempt_count,
                    last_strategy, started_at, finished_at, duration_ms,
                    error_code, error_message, created_at, updated_at, version, execution_scope
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.id,
                    state.job_id,
                    state.asset_id,
                    state.status.value,
                    state.active_result_id,
                    state.attempt_count,
                    state.last_strategy,
                    state.started_at,
                    state.finished_at,
                    state.duration_ms,
                    state.error_code,
                    state.error_message,
                    state.created_at,
                    state.updated_at,
                    state.version,
                    state.execution_scope,
                ),
            )
            return
        self._client.execute(
            """
            UPDATE job_asset_processing_states SET
                status = ?, active_result_id = ?, attempt_count = ?, last_strategy = ?,
                started_at = ?, finished_at = ?, duration_ms = ?, error_code = ?,
                error_message = ?, updated_at = ?, version = ?, execution_scope = ?
            WHERE job_id = ? AND asset_id = ?
            """,
            (
                state.status.value,
                state.active_result_id,
                state.attempt_count,
                state.last_strategy,
                state.started_at,
                state.finished_at,
                state.duration_ms,
                state.error_code,
                state.error_message,
                state.updated_at,
                state.version,
                state.execution_scope,
                state.job_id,
                state.asset_id,
            ),
        )

    def get_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> JobAssetProcessingState | None:
        rows = self._client.query(
            """
            SELECT id, job_id, asset_id, status, active_result_id, attempt_count,
                   last_strategy, started_at, finished_at, duration_ms,
                   error_code, error_message, created_at, updated_at, version, execution_scope
            FROM job_asset_processing_states
            WHERE job_id = ? AND asset_id = ?
            """,
            (job_id, asset_id),
        )
        if not rows:
            return None
        return _row_to_state(rows[0])

    def list_by_job(self, job_id: str) -> Sequence[JobAssetProcessingState]:
        rows = self._client.query(
            """
            SELECT id, job_id, asset_id, status, active_result_id, attempt_count,
                   last_strategy, started_at, finished_at, duration_ms,
                   error_code, error_message, created_at, updated_at, version, execution_scope
            FROM job_asset_processing_states
            WHERE job_id = ?
            ORDER BY created_at ASC
            """,
            (job_id,),
        )
        return [_row_to_state(r) for r in rows]

    def try_acquire(
        self,
        job_id: str,
        asset_id: str,
        *,
        expected_statuses: Sequence[JobAssetProcessingStatus],
        next_status: JobAssetProcessingStatus,
        strategy: str,
        now: datetime,
        worker_token: str | None = None,
    ) -> JobAssetProcessingState | None:
        if not expected_statuses:
            return None
        placeholders = ", ".join("?" for _ in expected_statuses)
        params: list[object] = [
            next_status.value,
            strategy,
            now,
            now,
            job_id,
            asset_id,
            *[s.value for s in expected_statuses],
        ]
        # Optimistic acquire: update only when status is still expected.
        self._client.execute(
            f"""
            UPDATE job_asset_processing_states
            SET status = ?, last_strategy = ?, started_at = ?, updated_at = ?,
                version = version + 1
            WHERE job_id = ? AND asset_id = ? AND status IN ({placeholders})
            """,
            tuple(params),
        )
        state = self.get_by_job_and_asset(job_id, asset_id)
        if state is None or state.status != next_status:
            return None
        return state

    def aggregate_progress(self, job_id: str) -> AssetProgressCounts:
        rows = self._client.query(
            """
            SELECT status, COUNT(1) AS cnt
            FROM job_asset_processing_states
            WHERE job_id = ?
            GROUP BY status
            """,
            (job_id,),
        )
        counts = {
            "PENDING": 0,
            "PROCESSING": 0,
            "RESOLVED": 0,
            "UNRECOGNIZED": 0,
            "FAILED_TECHNICAL": 0,
            "PENDING_MANUAL_REVIEW": 0,
            "CANCELLED": 0,
        }
        total = 0
        for row in rows:
            status = normalize_db_str(getattr(row, "status", None)) or ""
            cnt = int(getattr(row, "cnt", 0) or 0)
            total += cnt
            if status in counts:
                counts[status] = cnt
        return AssetProgressCounts(
            total=total,
            pending=counts["PENDING"],
            processing=counts["PROCESSING"],
            resolved=counts["RESOLVED"],
            unrecognized=counts["UNRECOGNIZED"],
            failed=counts["FAILED_TECHNICAL"],
            manual_review=counts["PENDING_MANUAL_REVIEW"],
            cancelled=counts["CANCELLED"],
        )

    def list_abandoned_processing(
        self, *, older_than: datetime, limit: int = 100
    ) -> Sequence[JobAssetProcessingState]:
        rows = self._client.query(
            """
            SELECT TOP (?) id, job_id, asset_id, status, active_result_id, attempt_count,
                   last_strategy, started_at, finished_at, duration_ms,
                   error_code, error_message, created_at, updated_at, version, execution_scope
            FROM job_asset_processing_states
            WHERE status = 'PROCESSING' AND updated_at < ?
            ORDER BY updated_at ASC
            """,
            (limit, older_than),
        )
        return [_row_to_state(r) for r in rows]
