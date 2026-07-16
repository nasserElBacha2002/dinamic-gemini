"""
SQL Server implementation of JobRepository — v3.0 (Épica 4).

Persists domain Job entities to the inventory_jobs table (normalized from v3_jobs in Stage 4).
get_latest_by_target: ORDER BY updated_at DESC, created_at DESC; returns single row.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.ports.repositories import JobRepository
from src.application.services.job_stale_reconciler import (
    STALE_FAILURE_CODE,
    STALE_FAILURE_MESSAGE,
    STALE_RECONCILE_STATUSES,
)
from src.database.sqlserver import SqlServerClient
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationStatus,
    LastCompletedFinalizationStep,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)

# Max target_ids per SQL ``IN`` clause (parameter-limit safety only — never caps jobs/runs).
TARGET_ID_BATCH_SIZE = 500


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _status_from_row(row, job_id: str = "?") -> JobStatus:
    raw = getattr(row, "status", None)
    if raw is None:
        status_str = "queued"
    elif isinstance(raw, str):
        status_str = raw.strip() or "queued"
    else:
        status_str = str(raw).strip() or "queued"
    try:
        return JobStatus(status_str)
    except ValueError:
        logger.warning(
            "Invalid job status from DB: %r, using QUEUED for job_id=%s",
            status_str,
            job_id,
        )
        return JobStatus.QUEUED


def _finalization_status_from_row(row: Any) -> FinalizationStatus:
    raw = getattr(row, "finalization_status", None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return FinalizationStatus.NOT_STARTED
    try:
        return FinalizationStatus(str(raw).strip())
    except ValueError:
        return FinalizationStatus.NOT_STARTED


def _current_finalization_step_from_row(row: Any) -> CurrentFinalizationStep | None:
    raw = getattr(row, "current_finalization_step", None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return CurrentFinalizationStep(str(raw).strip())
    except ValueError:
        return None


def _last_completed_step_from_row(row: Any) -> LastCompletedFinalizationStep:
    raw = getattr(row, "last_completed_finalization_step", None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return LastCompletedFinalizationStep.NONE
    try:
        return LastCompletedFinalizationStep(str(raw).strip())
    except ValueError:
        return LastCompletedFinalizationStep.NONE


def _parse_json(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        text = raw.strip()
    else:
        text = str(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_optional_json(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
    else:
        text = str(raw).strip()
    if not text:
        return None
    try:
        v = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(v, dict):
        return v
    return {"value": v}


# Fixed column projection for inventory_jobs reads (not user-controlled).
_JOB_SELECT_FIELDS = (
    "id, target_type, target_id, job_type, status, "
    "payload_json, result_json, error_message, created_at, updated_at, "
    "started_at, finished_at, last_heartbeat_at, cancel_requested_at, "
    "current_stage, current_substep, current_step_started_at, "
    "attempt_count, retry_of_job_id, failure_code, failure_message, execution_id, "
    "provider_name, model_name, prompt_key, engine_params_json, prompt_version, "
    "finalization_status, current_finalization_step, last_completed_finalization_step, "
    "finalization_error_code, finalization_error_metadata, finalization_started_at, "
    "finalization_completed_at, domain_persisted_at, artifacts_published_at"
)


def _row_to_job(row: Any) -> Job:
    jid = getattr(row, "id", "")
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None:
        logger.warning("inventory_jobs row missing created_at for job_id=%s", jid)
        raise ValueError("inventory_jobs row missing required created_at")
    if updated is None:
        logger.warning("inventory_jobs row missing updated_at for job_id=%s", jid)
        raise ValueError("inventory_jobs row missing required updated_at")
    return Job(
        id=jid,
        target_type=normalize_db_str(getattr(row, "target_type", None)),
        target_id=normalize_db_str(getattr(row, "target_id", None)),
        job_type=normalize_db_str(getattr(row, "job_type", None)),
        status=_status_from_row(row, jid),
        payload_json=_parse_json(getattr(row, "payload_json", None)),
        created_at=created,
        updated_at=updated,
        result_json=_parse_json(getattr(row, "result_json", None)) or None,
        error_message=getattr(row, "error_message", None),
        started_at=_ensure_utc(getattr(row, "started_at", None)),
        finished_at=_ensure_utc(getattr(row, "finished_at", None)),
        last_heartbeat_at=_ensure_utc(getattr(row, "last_heartbeat_at", None)),
        cancel_requested_at=_ensure_utc(getattr(row, "cancel_requested_at", None)),
        current_stage=getattr(row, "current_stage", None),
        current_substep=getattr(row, "current_substep", None),
        current_step_started_at=_ensure_utc(getattr(row, "current_step_started_at", None)),
        attempt_count=int(getattr(row, "attempt_count", 1) or 1),
        retry_of_job_id=getattr(row, "retry_of_job_id", None),
        failure_code=getattr(row, "failure_code", None),
        failure_message=getattr(row, "failure_message", None),
        execution_id=getattr(row, "execution_id", None),
        provider_name=getattr(row, "provider_name", None),
        model_name=getattr(row, "model_name", None),
        prompt_key=getattr(row, "prompt_key", None),
        engine_params_json=_parse_optional_json(getattr(row, "engine_params_json", None)),
        prompt_version=getattr(row, "prompt_version", None),
        finalization_status=_finalization_status_from_row(row),
        current_finalization_step=_current_finalization_step_from_row(row),
        last_completed_finalization_step=_last_completed_step_from_row(row),
        finalization_error_code=getattr(row, "finalization_error_code", None),
        finalization_error_metadata=_parse_optional_json(
            getattr(row, "finalization_error_metadata", None)
        ),
        finalization_started_at=_ensure_utc(getattr(row, "finalization_started_at", None)),
        finalization_completed_at=_ensure_utc(getattr(row, "finalization_completed_at", None)),
        domain_persisted_at=_ensure_utc(getattr(row, "domain_persisted_at", None)),
        artifacts_published_at=_ensure_utc(getattr(row, "artifacts_published_at", None)),
    )


class SqlJobRepository(JobRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, job: Job) -> None:
        if job.created_at is None or job.updated_at is None:
            raise ValueError("Job created_at and updated_at are required")
        created = _ensure_utc(job.created_at)
        updated = _ensure_utc(job.updated_at)
        payload_str = json.dumps(job.payload_json, ensure_ascii=False) if job.payload_json else None
        result_str = json.dumps(job.result_json, ensure_ascii=False) if job.result_json else None
        engine_str = (
            json.dumps(job.engine_params_json, ensure_ascii=False)
            if job.engine_params_json
            else None
        )
        finalization_meta_str = (
            json.dumps(job.finalization_error_metadata, ensure_ascii=False)
            if job.finalization_error_metadata
            else None
        )
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET target_type = ?, target_id = ?, job_type = ?, status = ?,
                    payload_json = ?, result_json = ?, error_message = ?, updated_at = ?,
                    started_at = ?, finished_at = ?, last_heartbeat_at = ?, cancel_requested_at = ?,
                    current_stage = ?, current_substep = ?, current_step_started_at = ?,
                    attempt_count = ?, retry_of_job_id = ?, failure_code = ?, failure_message = ?, execution_id = ?,
                    provider_name = ?, model_name = ?, prompt_key = ?, engine_params_json = ?,
                    prompt_version = ?,
                    finalization_status = ?, current_finalization_step = ?,
                    last_completed_finalization_step = ?, finalization_error_code = ?,
                    finalization_error_metadata = ?, finalization_started_at = ?,
                    finalization_completed_at = ?, domain_persisted_at = ?, artifacts_published_at = ?
                WHERE id = ?
                """,
                (
                    job.target_type,
                    job.target_id,
                    job.job_type,
                    job.status.value,
                    payload_str,
                    result_str,
                    job.error_message,
                    updated,
                    _ensure_utc(job.started_at),
                    _ensure_utc(job.finished_at),
                    _ensure_utc(job.last_heartbeat_at),
                    _ensure_utc(job.cancel_requested_at),
                    job.current_stage,
                    job.current_substep,
                    _ensure_utc(job.current_step_started_at),
                    int(job.attempt_count or 1),
                    job.retry_of_job_id,
                    job.failure_code,
                    job.failure_message,
                    job.execution_id,
                    job.provider_name,
                    job.model_name,
                    job.prompt_key,
                    engine_str,
                    job.prompt_version,
                    job.finalization_status.value,
                    job.current_finalization_step.value if job.current_finalization_step else None,
                    job.last_completed_finalization_step.value,
                    job.finalization_error_code,
                    finalization_meta_str,
                    _ensure_utc(job.finalization_started_at),
                    _ensure_utc(job.finalization_completed_at),
                    _ensure_utc(job.domain_persisted_at),
                    _ensure_utc(job.artifacts_published_at),
                    job.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO inventory_jobs (id, target_type, target_id, job_type, status,
                        payload_json, result_json, error_message, created_at, updated_at,
                        started_at, finished_at, last_heartbeat_at, cancel_requested_at,
                        current_stage, current_substep, current_step_started_at,
                        attempt_count, retry_of_job_id, failure_code, failure_message, execution_id,
                        provider_name, model_name, prompt_key, engine_params_json, prompt_version,
                        finalization_status, current_finalization_step, last_completed_finalization_step,
                        finalization_error_code, finalization_error_metadata, finalization_started_at,
                        finalization_completed_at, domain_persisted_at, artifacts_published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.id,
                        job.target_type,
                        job.target_id,
                        job.job_type,
                        job.status.value,
                        payload_str,
                        result_str,
                        job.error_message,
                        created,
                        updated,
                        _ensure_utc(job.started_at),
                        _ensure_utc(job.finished_at),
                        _ensure_utc(job.last_heartbeat_at),
                        _ensure_utc(job.cancel_requested_at),
                        job.current_stage,
                        job.current_substep,
                        _ensure_utc(job.current_step_started_at),
                        int(job.attempt_count or 1),
                        job.retry_of_job_id,
                        job.failure_code,
                        job.failure_message,
                        job.execution_id,
                        job.provider_name,
                        job.model_name,
                        job.prompt_key,
                        engine_str,
                        job.prompt_version,
                        job.finalization_status.value,
                        job.current_finalization_step.value if job.current_finalization_step else None,
                        job.last_completed_finalization_step.value,
                        job.finalization_error_code,
                        finalization_meta_str,
                        _ensure_utc(job.finalization_started_at),
                        _ensure_utc(job.finalization_completed_at),
                        _ensure_utc(job.domain_persisted_at),
                        _ensure_utc(job.artifacts_published_at),
                    ),
                )

    def get_by_id(self, job_id: str) -> Job | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_JOB_SELECT_FIELDS} FROM inventory_jobs WHERE id = ?",  # nosec B608
                (job_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_job(row)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT TOP 1 {_JOB_SELECT_FIELDS}
                FROM inventory_jobs
                WHERE target_type = ? AND target_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,  # nosec B608
                (target_type, target_id),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_job(row)

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        # TOP n: n clamped 1..500 in Python (not request text concatenation).
        # UI/history only — never use for billable cost aggregation.
        n = max(1, min(int(limit), 500))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT TOP ({n}) {_JOB_SELECT_FIELDS}
                FROM inventory_jobs
                WHERE target_type = ? AND target_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,  # nosec B608
                (target_type, target_id),
            )
            rows = cur.fetchall()
        return [_row_to_job(row) for row in rows]

    def list_jobs_for_targets(
        self,
        target_type: str,
        target_ids: Sequence[str],
        *,
        job_type: str | None = None,
    ) -> Sequence[Job]:
        """All matching jobs for targets — no per-aisle history truncation.

        Batches ``target_id IN (...)`` lists to stay under SQL Server parameter limits.
        Does not cap the number of jobs returned per target.
        """
        if not target_ids:
            return []
        unique_ids = list(dict.fromkeys(target_ids))
        out: list[Job] = []
        seen: set[str] = set()
        for start in range(0, len(unique_ids), TARGET_ID_BATCH_SIZE):
            batch = unique_ids[start : start + TARGET_ID_BATCH_SIZE]
            placeholders = ",".join("?" * len(batch))
            params: list[Any] = [target_type, *batch]
            job_type_sql = ""
            if job_type is not None:
                job_type_sql = "AND job_type = ?"
                params.append(job_type)
            query = f"""
                SELECT {_JOB_SELECT_FIELDS}
                FROM inventory_jobs
                WHERE target_type = ?
                  AND target_id IN ({placeholders})
                  {job_type_sql}
                ORDER BY target_id, updated_at DESC, created_at DESC
            """  # nosec B608
            with self._client.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
            for row in rows:
                job = _row_to_job(row)
                if job.id in seen:
                    continue
                seen.add(job.id)
                out.append(job)
        return out

    def list_all_jobs(self) -> Sequence[Job]:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_JOB_SELECT_FIELDS} FROM inventory_jobs ORDER BY updated_at DESC, created_at DESC"  # nosec B608
            )
            rows = cur.fetchall()
        return [_row_to_job(row) for row in rows]

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> dict[str, Job]:
        if not target_ids:
            return {}
        # IN clause placeholders only; target_ids bound as parameters (no raw concatenation).
        placeholders = ",".join("?" * len(target_ids))
        params: list[Any] = [target_type, *target_ids]
        query = f"""
            SELECT {_JOB_SELECT_FIELDS}
            FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY target_id ORDER BY updated_at DESC, created_at DESC
                ) AS rn
                FROM inventory_jobs
                WHERE target_type = ? AND target_id IN ({placeholders})
            ) t
            WHERE t.rn = 1
        """  # nosec B608
        with self._client.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return {row.target_id: _row_to_job(row) for row in rows}

    def list_jobs_for_metrics(
        self,
        *,
        created_from: datetime,
        created_to: datetime,
        job_type: str = "process_aisle",
        target_type: str = "aisle",
        limit: int = 5000,
    ) -> Sequence[Job]:
        cf = _ensure_utc(created_from)
        ct = _ensure_utc(created_to)
        if cf is None or ct is None:
            return []
        n = max(1, min(int(limit), 10_000))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT TOP ({n}) {_JOB_SELECT_FIELDS}
                FROM inventory_jobs
                WHERE job_type = ? AND target_type = ?
                  AND created_at >= ? AND created_at <= ?
                ORDER BY created_at DESC
                """,  # nosec B608
                (job_type, target_type, cf, ct),
            )
            rows = cur.fetchall()
        return [_row_to_job(row) for row in rows]

    def list_jobs_for_metrics_by_finished_at(
        self,
        *,
        finished_from: datetime,
        finished_to: datetime,
        job_type: str = "process_aisle",
        target_type: str = "aisle",
        limit: int = 5000,
    ) -> Sequence[Job]:
        ff = _ensure_utc(finished_from)
        ft = _ensure_utc(finished_to)
        if ff is None or ft is None:
            return []
        n = max(1, min(int(limit), 10_000))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT TOP ({n}) {_JOB_SELECT_FIELDS}
                FROM inventory_jobs
                WHERE job_type = ? AND target_type = ?
                  AND finished_at IS NOT NULL
                  AND finished_at >= ? AND finished_at <= ?
                ORDER BY finished_at DESC
                """,  # nosec B608
                (job_type, target_type, ff, ft),
            )
            rows = cur.fetchall()
        return [_row_to_job(row) for row in rows]

    def claim_next_queued_job(self) -> Job | None:
        """Atomically claim next queued v3 job from `inventory_jobs`.

        This is used by the standalone worker flow so API and worker share
        the same persisted v3 job source.
        """
        claimed_job_id: str | None = None
        with self._client.cursor() as cur:
            cur.execute(
                """
                ;WITH next_job AS (
                    SELECT TOP 1 id
                    FROM inventory_jobs WITH (UPDLOCK, READPAST, ROWLOCK)
                    WHERE status = 'queued'
                    ORDER BY created_at ASC, id ASC
                )
                UPDATE inventory_jobs
                SET updated_at = ?, status = ?, started_at = COALESCE(started_at, ?)
                OUTPUT inserted.id
                WHERE id IN (SELECT id FROM next_job)
                """,
                (datetime.now(timezone.utc), JobStatus.STARTING.value, datetime.now(timezone.utc)),
            )
            row = cur.fetchone()
            if row is not None:
                raw_id = getattr(row, "id", None)
                if raw_id is None:
                    try:
                        raw_id = row[0]
                    except Exception:
                        raw_id = None
                if raw_id is not None:
                    claimed_job_id = str(raw_id)
        if not claimed_job_id:
            return None
        return self.get_by_id(claimed_job_id)

    def reclaim_stale_running_jobs(self, stale_after_seconds: int) -> int:
        """Fail stale active jobs using the shared stale-reconciliation contract."""
        if stale_after_seconds <= 0:
            return 0
        # IN (?,?,?) must stay aligned with STALE_RECONCILE_STATUSES (three terminal states).
        status_values = tuple(s.value for s in STALE_RECONCILE_STATUSES)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET status = 'failed',
                    updated_at = ?,
                    finished_at = ?,
                    failure_code = ?,
                    failure_message = ?,
                    error_message = ?
                WHERE status IN (?, ?, ?)
                  AND DATEDIFF(SECOND, COALESCE(last_heartbeat_at, updated_at), ?) >= ?
                """,
                (
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                    STALE_FAILURE_CODE,
                    STALE_FAILURE_MESSAGE,
                    STALE_FAILURE_MESSAGE,
                    *status_values,
                    datetime.now(timezone.utc),
                    stale_after_seconds,
                ),
            )
            return int(cur.rowcount or 0)
