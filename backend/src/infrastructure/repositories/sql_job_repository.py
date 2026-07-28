"""
SQL Server implementation of JobRepository — v3.0 (Épica 4).

Persists domain Job entities to the inventory_jobs table (normalized from v3_jobs in Stage 4).
get_latest_by_target: ORDER BY updated_at DESC, created_at DESC; returns single row.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from src.application.ports.repositories import JobRepository
from src.application.services.job_claim_helpers import classify_claim_after_cas_miss
from src.application.services.job_lease_helpers import (
    classify_lease_renewal_after_cas_miss,
    classify_lease_write_after_cas_miss,
    lease_allows_finalization_write,
    lease_is_currently_valid,
)
from src.application.services.job_stale_reconciler import (
    STALE_FAILURE_CODE,
    STALE_FAILURE_MESSAGE,
    STALE_RECONCILE_STATUSES,
)
from src.database.sqlserver import SqlServerClient
from src.domain.aisle.entities import AisleStatus
from src.domain.aisle_identification.modes import (
    CONFIGURATION_SNAPSHOT_VERSION,
    historical_job_execution_strategy,
    historical_job_identification_mode,
    historical_job_identification_mode_source,
)
from src.domain.jobs.claim import (
    TERMINAL_JOB_STATUSES,
    JobClaimOutcome,
    JobClaimResult,
    StaleReclaimResult,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationStatus,
    LastCompletedFinalizationStep,
)
from src.domain.jobs.lease import (
    JobLease,
    LeaseRenewalOutcome,
    LeaseRenewalResult,
    LeaseWriteOutcome,
    LeaseWriteResult,
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
    "attempt_count, retry_of_job_id, failure_code, failure_message, execution_id, claim_owner_id, "
    "provider_name, model_name, prompt_key, engine_params_json, prompt_version, "
    "identification_mode, identification_mode_source, configuration_snapshot_version, "
    "execution_strategy, "
    "finalization_status, current_finalization_step, last_completed_finalization_step, "
    "finalization_error_code, finalization_error_metadata, finalization_started_at, "
    "finalization_completed_at, domain_persisted_at, artifacts_published_at, "
    "lease_fencing_token, lease_expires_at, lease_acquired_at"
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
        claim_owner_id=getattr(row, "claim_owner_id", None),
        provider_name=getattr(row, "provider_name", None),
        model_name=getattr(row, "model_name", None),
        prompt_key=getattr(row, "prompt_key", None),
        engine_params_json=_parse_optional_json(getattr(row, "engine_params_json", None)),
        prompt_version=getattr(row, "prompt_version", None),
        identification_mode=historical_job_identification_mode(
            getattr(row, "identification_mode", None)
        ),
        identification_mode_source=historical_job_identification_mode_source(
            getattr(row, "identification_mode_source", None)
        ),
        configuration_snapshot_version=int(
            getattr(row, "configuration_snapshot_version", None)
            or CONFIGURATION_SNAPSHOT_VERSION
        ),
        execution_strategy=historical_job_execution_strategy(
            getattr(row, "execution_strategy", None)
        ),
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
        lease_fencing_token=int(getattr(row, "lease_fencing_token", 0) or 0),
        lease_expires_at=_ensure_utc(getattr(row, "lease_expires_at", None)),
        lease_acquired_at=_ensure_utc(getattr(row, "lease_acquired_at", None)),
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
                    claim_owner_id = ?,
                    provider_name = ?, model_name = ?, prompt_key = ?, engine_params_json = ?,
                    prompt_version = ?,
                    identification_mode = ?, identification_mode_source = ?,
                    configuration_snapshot_version = ?, execution_strategy = ?,
                    finalization_status = ?, current_finalization_step = ?,
                    last_completed_finalization_step = ?, finalization_error_code = ?,
                    finalization_error_metadata = ?, finalization_started_at = ?,
                    finalization_completed_at = ?, domain_persisted_at = ?, artifacts_published_at = ?,
                    lease_fencing_token = ?, lease_expires_at = ?, lease_acquired_at = ?
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
                    job.claim_owner_id,
                    job.provider_name,
                    job.model_name,
                    job.prompt_key,
                    engine_str,
                    job.prompt_version,
                    job.identification_mode.value,
                    job.identification_mode_source.value,
                    int(job.configuration_snapshot_version or CONFIGURATION_SNAPSHOT_VERSION),
                    job.execution_strategy.value,
                    job.finalization_status.value,
                    job.current_finalization_step.value if job.current_finalization_step else None,
                    job.last_completed_finalization_step.value,
                    job.finalization_error_code,
                    finalization_meta_str,
                    _ensure_utc(job.finalization_started_at),
                    _ensure_utc(job.finalization_completed_at),
                    _ensure_utc(job.domain_persisted_at),
                    _ensure_utc(job.artifacts_published_at),
                    int(job.lease_fencing_token or 0),
                    _ensure_utc(job.lease_expires_at),
                    _ensure_utc(job.lease_acquired_at),
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
                        claim_owner_id,
                        provider_name, model_name, prompt_key, engine_params_json, prompt_version,
                        identification_mode, identification_mode_source,
                        configuration_snapshot_version, execution_strategy,
                        finalization_status, current_finalization_step, last_completed_finalization_step,
                        finalization_error_code, finalization_error_metadata, finalization_started_at,
                        finalization_completed_at, domain_persisted_at, artifacts_published_at,
                        lease_fencing_token, lease_expires_at, lease_acquired_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        job.claim_owner_id,
                        job.provider_name,
                        job.model_name,
                        job.prompt_key,
                        engine_str,
                        job.prompt_version,
                        job.identification_mode.value,
                        job.identification_mode_source.value,
                        int(job.configuration_snapshot_version or CONFIGURATION_SNAPSHOT_VERSION),
                        job.execution_strategy.value,
                        job.finalization_status.value,
                        job.current_finalization_step.value if job.current_finalization_step else None,
                        job.last_completed_finalization_step.value,
                        job.finalization_error_code,
                        finalization_meta_str,
                        _ensure_utc(job.finalization_started_at),
                        _ensure_utc(job.finalization_completed_at),
                        _ensure_utc(job.domain_persisted_at),
                        _ensure_utc(job.artifacts_published_at),
                        int(job.lease_fencing_token or 0),
                        _ensure_utc(job.lease_expires_at),
                        _ensure_utc(job.lease_acquired_at),
                    ),
                )

    def merge_result_json(self, job_id: str, patch: dict[str, Any]) -> Job | None:
        """Merge top-level ``result_json`` keys under a row lock (Phase 2 asset_progress).

        Uses ``UPDLOCK, ROWLOCK`` so a concurrent full ``save()`` of other fields cannot
        silently drop the merged keys between read and write of ``result_json``.
        """
        if not patch:
            return self.get_by_id(job_id)
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT result_json
                FROM inventory_jobs WITH (UPDLOCK, ROWLOCK)
                WHERE id = ?
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            current = _parse_json(getattr(row, "result_json", None)) or {}
            if not isinstance(current, dict):
                current = {}
            merged = dict(current)
            merged.update(patch)
            cur.execute(
                """
                UPDATE inventory_jobs
                SET result_json = ?, updated_at = SYSUTCDATETIME()
                WHERE id = ?
                """,
                (json.dumps(merged, ensure_ascii=False), job_id),
            )
        return self.get_by_id(job_id)

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

    def try_claim_starting_to_running(
        self,
        job_id: str,
        *,
        now: datetime,
        claim_owner_id: str,
        aisle_id: str,
        lease_duration_seconds: int = 60,
    ) -> JobClaimResult:
        """CAS STARTING → RUNNING + aisle PROCESSING in one transaction.

        Phase 3: also acquires a lease (fencing token incremented, expiry set from
        ``lease_duration_seconds``) attached to the returned ``JobClaimResult.lease``.
        """
        owner = (claim_owner_id or "").strip()
        if not owner:
            return JobClaimResult(
                outcome=JobClaimOutcome.CONFLICT,
                reason="claim_owner_id_required",
                claim_owner_id=None,
            )
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        lease_duration = max(1, int(lease_duration_seconds or 60))
        lease_expires_at = now_utc + timedelta(seconds=lease_duration)
        acquired = False
        aisle_applied = False
        acquired_fencing_token: int | None = None
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            try:
                # Validate job target under lock.
                cur.execute(
                    """
                    SELECT target_type, target_id, status
                    FROM inventory_jobs WITH (UPDLOCK, ROWLOCK)
                    WHERE id = ?
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
                if row is None:
                    txn.rollback()
                    return JobClaimResult(
                        outcome=JobClaimOutcome.NOT_FOUND,
                        reason="job_not_found",
                        claim_owner_id=owner,
                    )
                target_type = str(getattr(row, "target_type", None) or row[0])
                target_id = str(getattr(row, "target_id", None) or row[1])
                status = str(getattr(row, "status", None) or row[2])
                if target_type != "aisle" or target_id != aisle_id:
                    txn.rollback()
                    return JobClaimResult(
                        outcome=JobClaimOutcome.TARGET_MISMATCH,
                        previous_status=status,
                        reason="job_aisle_mismatch",
                        claim_owner_id=owner,
                    )
                if status in (
                    JobStatus.SUCCEEDED.value,
                    JobStatus.FAILED.value,
                    JobStatus.CANCELED.value,
                    JobStatus.TIMED_OUT.value,
                ):
                    txn.rollback()
                    return JobClaimResult(
                        outcome=JobClaimOutcome.TERMINAL,
                        previous_status=status,
                        reason="job_terminal",
                        claim_owner_id=owner,
                    )

                cur.execute(
                    """
                    SELECT status
                    FROM aisles WITH (UPDLOCK, ROWLOCK)
                    WHERE id = ?
                    """,
                    (aisle_id,),
                )
                aisle_row = cur.fetchone()
                if aisle_row is None:
                    txn.rollback()
                    return JobClaimResult(
                        outcome=JobClaimOutcome.TARGET_NOT_FOUND,
                        previous_status=status,
                        reason="aisle_not_found",
                        claim_owner_id=owner,
                    )
                aisle_status = str(getattr(aisle_row, "status", None) or aisle_row[0])
                if aisle_status not in (
                    AisleStatus.QUEUED.value,
                    AisleStatus.ASSETS_UPLOADED.value,
                    AisleStatus.PROCESSING.value,
                ):
                    txn.rollback()
                    return JobClaimResult(
                        outcome=JobClaimOutcome.TARGET_INVALID_STATUS,
                        previous_status=status,
                        reason=f"aisle_status:{aisle_status}",
                        claim_owner_id=owner,
                    )

                cur.execute(
                    """
                    UPDATE inventory_jobs
                    SET status = ?,
                        claim_owner_id = ?,
                        started_at = COALESCE(started_at, ?),
                        last_heartbeat_at = ?,
                        current_stage = ?,
                        current_substep = ?,
                        current_step_started_at = ?,
                        updated_at = ?,
                        lease_fencing_token = lease_fencing_token + 1,
                        lease_acquired_at = ?,
                        lease_expires_at = ?
                    OUTPUT inserted.lease_fencing_token
                    WHERE id = ?
                      AND status = ?
                    """,
                    (
                        JobStatus.RUNNING.value,
                        owner,
                        now_utc,
                        now_utc,
                        "Pipeline",
                        "startup_confirmed",
                        now_utc,
                        now_utc,
                        now_utc,
                        lease_expires_at,
                        job_id,
                        JobStatus.STARTING.value,
                    ),
                )
                cas_row = cur.fetchone()
                if cas_row is not None:
                    raw_token = getattr(cas_row, "lease_fencing_token", None)
                    if raw_token is None:
                        try:
                            raw_token = cas_row[0]
                        except Exception:
                            raw_token = None
                    if raw_token is not None:
                        acquired_fencing_token = int(raw_token)
                acquired = acquired_fencing_token is not None or int(cur.rowcount or 0) == 1
                if acquired:
                    cur.execute(
                        """
                        UPDATE aisles
                        SET status = ?,
                            updated_at = ?,
                            error_code = NULL,
                            error_message = NULL,
                            retryable = NULL
                        WHERE id = ?
                          AND status IN (?, ?, ?)
                        """,
                        (
                            AisleStatus.PROCESSING.value,
                            now_utc,
                            aisle_id,
                            AisleStatus.QUEUED.value,
                            AisleStatus.ASSETS_UPLOADED.value,
                            AisleStatus.PROCESSING.value,
                        ),
                    )
                    aisle_applied = int(cur.rowcount or 0) == 1
                    if not aisle_applied:
                        txn.rollback()
                        return JobClaimResult(
                            outcome=JobClaimOutcome.TARGET_INVALID_STATUS,
                            reason="aisle_update_rowcount_zero",
                            claim_owner_id=owner,
                        )
                    txn.commit()
                else:
                    txn.rollback()
            except Exception:
                txn.rollback()
                raise
            finally:
                cur.close()

        if acquired:
            job = self.get_by_id(job_id)
            fencing_token = (
                acquired_fencing_token
                if acquired_fencing_token is not None
                else int(getattr(job, "lease_fencing_token", 0) or 0)
            )
            lease = JobLease(
                job_id=job_id,
                owner_id=owner,
                fencing_token=fencing_token,
                acquired_at=now_utc,
                expires_at=lease_expires_at,
            )
            logger.info(
                "event=job_claim_acquired job_id=%s aisle_id=%s claim_owner_id=%s "
                "previous_status=starting new_status=running attempt=%s",
                job_id,
                aisle_id,
                owner,
                getattr(job, "attempt_count", None) if job else None,
            )
            logger.info(
                "event=job_lease_acquired job_id=%s owner_id=%s fencing_token=%s expires_at=%s",
                job_id,
                owner,
                fencing_token,
                lease_expires_at.isoformat(),
            )
            return JobClaimResult(
                outcome=JobClaimOutcome.ACQUIRED,
                job=job,
                aisle_transition_applied=True,
                previous_status=JobStatus.STARTING.value,
                reason="cas_acquired",
                claim_owner_id=owner,
                lease=lease,
            )

        job = self.get_by_id(job_id)
        result = classify_claim_after_cas_miss(job, claim_owner_id=owner)
        if result.outcome == JobClaimOutcome.ALREADY_OWNED:
            # Idempotent: ensure aisle PROCESSING outside the lost CAS txn.
            with self._client.cursor() as cur:
                cur.execute(
                    """
                    UPDATE aisles
                    SET status = ?,
                        updated_at = ?,
                        error_code = NULL,
                        error_message = NULL,
                        retryable = NULL
                    WHERE id = ?
                      AND status IN (?, ?, ?)
                    """,
                    (
                        AisleStatus.PROCESSING.value,
                        now_utc,
                        aisle_id,
                        AisleStatus.QUEUED.value,
                        AisleStatus.ASSETS_UPLOADED.value,
                        AisleStatus.PROCESSING.value,
                    ),
                )
                aisle_applied = int(cur.rowcount or 0) >= 0
            current_lease = None
            if (
                job is not None
                and job.lease_expires_at is not None
                and job.lease_acquired_at is not None
            ):
                current_lease = JobLease(
                    job_id=job_id,
                    owner_id=owner,
                    fencing_token=int(job.lease_fencing_token or 0),
                    acquired_at=job.lease_acquired_at,
                    expires_at=job.lease_expires_at,
                )
            return JobClaimResult(
                outcome=JobClaimOutcome.ALREADY_OWNED,
                job=job,
                aisle_transition_applied=True,
                previous_status=result.previous_status,
                reason=result.reason,
                claim_owner_id=owner,
                lease=current_lease,
            )
        logger.info(
            "event=job_claim_rejected job_id=%s claim_owner_id=%s reason=%s "
            "current_status=%s current_owner=%s",
            job_id,
            owner,
            result.reason,
            result.previous_status,
            getattr(job, "claim_owner_id", None) if job else None,
        )
        return result

    def renew_lease(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        """Extend ``lease_expires_at`` under CAS (owner + fencing_token + not-yet-expired)."""
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        duration = max(1, int(extension_seconds or 0))
        new_expires_at = now_utc + timedelta(seconds=duration)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET lease_expires_at = ?, last_heartbeat_at = ?, updated_at = ?
                WHERE id = ?
                  AND status IN (?, ?)
                  AND claim_owner_id = ?
                  AND lease_fencing_token = ?
                  AND lease_expires_at >= ?
                """,
                (
                    new_expires_at,
                    now_utc,
                    now_utc,
                    lease.job_id,
                    JobStatus.RUNNING.value,
                    JobStatus.CANCEL_REQUESTED.value,
                    lease.owner_id,
                    lease.fencing_token,
                    now_utc,
                ),
            )
            applied = int(cur.rowcount or 0) == 1

        if applied:
            renewed = JobLease(
                job_id=lease.job_id,
                owner_id=lease.owner_id,
                fencing_token=lease.fencing_token,
                acquired_at=lease.acquired_at,
                expires_at=new_expires_at,
            )
            logger.info(
                "event=job_lease_renewed job_id=%s owner_id=%s fencing_token=%s expires_at=%s",
                lease.job_id,
                lease.owner_id,
                lease.fencing_token,
                new_expires_at.isoformat(),
            )
            return LeaseRenewalResult(outcome=LeaseRenewalOutcome.RENEWED, lease=renewed)

        job = self.get_by_id(lease.job_id)
        result = classify_lease_renewal_after_cas_miss(
            job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        )
        logger.warning(
            "event=job_lease_lost job_id=%s owner_id=%s fencing_token=%s outcome=%s reason=%s",
            lease.job_id,
            lease.owner_id,
            lease.fencing_token,
            result.outcome.value,
            result.reason,
        )
        return result

    def reacquire_expired_lease(
        self,
        job_id: str,
        *,
        now: datetime,
        new_owner_id: str,
        extension_seconds: int,
    ) -> JobClaimResult:
        """Steal an expired RUNNING lease: new owner + fencing_token + 1."""
        owner = (new_owner_id or "").strip()
        if not owner:
            return JobClaimResult(
                outcome=JobClaimOutcome.CONFLICT,
                reason="claim_owner_id_required",
                claim_owner_id=None,
            )
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        duration = max(1, int(extension_seconds or 0))
        new_expires_at = now_utc + timedelta(seconds=duration)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET claim_owner_id = ?,
                    lease_fencing_token = lease_fencing_token + 1,
                    lease_acquired_at = ?,
                    lease_expires_at = ?,
                    last_heartbeat_at = ?,
                    updated_at = ?
                OUTPUT inserted.lease_fencing_token
                WHERE id = ?
                  AND status = ?
                  AND lease_expires_at < ?
                """,
                (
                    owner,
                    now_utc,
                    new_expires_at,
                    now_utc,
                    now_utc,
                    job_id,
                    JobStatus.RUNNING.value,
                    now_utc,
                ),
            )
            row = cur.fetchone()
        if row is None:
            job = self.get_by_id(job_id)
            if job is None:
                return JobClaimResult(
                    outcome=JobClaimOutcome.NOT_FOUND, reason="job_not_found", claim_owner_id=owner
                )
            status_value = job.status.value if isinstance(job.status, JobStatus) else str(job.status)
            if status_value in TERMINAL_JOB_STATUSES:
                return JobClaimResult(
                    outcome=JobClaimOutcome.TERMINAL,
                    job=job,
                    previous_status=status_value,
                    reason="job_terminal",
                    claim_owner_id=owner,
                )
            return JobClaimResult(
                outcome=JobClaimOutcome.CONFLICT,
                job=job,
                previous_status=status_value,
                reason="lease_not_expired_or_not_running",
                claim_owner_id=owner,
            )

        raw_token = getattr(row, "lease_fencing_token", None)
        if raw_token is None:
            try:
                raw_token = row[0]
            except Exception:
                raw_token = None
        fencing_token = int(raw_token) if raw_token is not None else 0
        job = self.get_by_id(job_id)
        lease = JobLease(
            job_id=job_id,
            owner_id=owner,
            fencing_token=fencing_token,
            acquired_at=now_utc,
            expires_at=new_expires_at,
        )
        logger.warning(
            "event=job_lease_reacquired job_id=%s new_owner_id=%s fencing_token=%s expires_at=%s",
            job_id,
            owner,
            fencing_token,
            new_expires_at.isoformat(),
        )
        return JobClaimResult(
            outcome=JobClaimOutcome.ACQUIRED,
            job=job,
            reason="lease_reacquired",
            claim_owner_id=owner,
            lease=lease,
        )

    def merge_result_json_if_leased(
        self,
        lease: JobLease,
        patch: dict[str, Any],
        *,
        now: datetime,
    ) -> tuple[LeaseWriteResult, Job | None]:
        """Merge ``result_json`` only while the caller still holds the lease (owner+token+not expired)."""
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        if not patch:
            job = self.get_by_id(lease.job_id)
            if lease_is_currently_valid(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
            ):
                return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED), job
            result = classify_lease_write_after_cas_miss(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
            )
            return result, job

        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            try:
                cur.execute(
                    """
                    SELECT result_json, status, claim_owner_id, lease_fencing_token, lease_expires_at
                    FROM inventory_jobs WITH (UPDLOCK, ROWLOCK)
                    WHERE id = ?
                    """,
                    (lease.job_id,),
                )
                row = cur.fetchone()
                if row is None:
                    txn.rollback()
                    return (
                        LeaseWriteResult(outcome=LeaseWriteOutcome.NOT_FOUND, reason="job_not_found"),
                        None,
                    )

                status_value = str(getattr(row, "status", None) or "")
                persisted_owner = normalize_db_str(getattr(row, "claim_owner_id", None))
                persisted_token = int(getattr(row, "lease_fencing_token", 0) or 0)
                expires_at = _ensure_utc(getattr(row, "lease_expires_at", None))

                if status_value in TERMINAL_JOB_STATUSES:
                    txn.rollback()
                    logger.warning(
                        "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                        "reason=job_terminal",
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                    )
                    return (
                        LeaseWriteResult(
                            outcome=LeaseWriteOutcome.JOB_TERMINAL,
                            reason=f"job_terminal:{status_value}",
                        ),
                        self.get_by_id(lease.job_id),
                    )
                if status_value not in (JobStatus.RUNNING.value, JobStatus.CANCEL_REQUESTED.value):
                    txn.rollback()
                    logger.warning(
                        "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                        "reason=invalid_state:%s",
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                        status_value,
                    )
                    return (
                        LeaseWriteResult(
                            outcome=LeaseWriteOutcome.INVALID_STATE,
                            reason=f"status_not_leasable:{status_value}",
                        ),
                        self.get_by_id(lease.job_id),
                    )
                if (
                    persisted_owner != (lease.owner_id or "").strip()
                    or persisted_token != lease.fencing_token
                ):
                    txn.rollback()
                    logger.warning(
                        "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                        "persisted_owner=%s persisted_token=%s reason=owner_or_fencing_token_mismatch",
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                        persisted_owner,
                        persisted_token,
                    )
                    return (
                        LeaseWriteResult(
                            outcome=LeaseWriteOutcome.LEASE_LOST,
                            reason="owner_or_fencing_token_mismatch",
                        ),
                        self.get_by_id(lease.job_id),
                    )
                if expires_at is not None and expires_at < now_utc:
                    txn.rollback()
                    logger.warning(
                        "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                        "reason=lease_expired",
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                    )
                    return (
                        LeaseWriteResult(outcome=LeaseWriteOutcome.LEASE_LOST, reason="lease_expired"),
                        self.get_by_id(lease.job_id),
                    )

                current = _parse_json(getattr(row, "result_json", None)) or {}
                if not isinstance(current, dict):
                    current = {}
                merged = dict(current)
                merged.update(patch)
                cur.execute(
                    """
                    UPDATE inventory_jobs
                    SET result_json = ?, updated_at = ?
                    WHERE id = ?
                      AND claim_owner_id = ?
                      AND lease_fencing_token = ?
                      AND lease_expires_at >= ?
                      AND status IN (?, ?)
                    """,
                    (
                        json.dumps(merged, ensure_ascii=False),
                        now_utc,
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                        now_utc,
                        JobStatus.RUNNING.value,
                        JobStatus.CANCEL_REQUESTED.value,
                    ),
                )
                if int(cur.rowcount or 0) != 1:
                    txn.rollback()
                    job = self.get_by_id(lease.job_id)
                    result = classify_lease_write_after_cas_miss(
                        job,
                        owner_id=lease.owner_id,
                        fencing_token=lease.fencing_token,
                        now=now_utc,
                    )
                    logger.warning(
                        "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                        "outcome=%s reason=%s",
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                        result.outcome.value,
                        result.reason,
                    )
                    return result, job
                txn.commit()
            except Exception:
                txn.rollback()
                raise
            finally:
                cur.close()
        return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED), self.get_by_id(lease.job_id)

    def touch_heartbeat_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        """Renew lease + update ``last_heartbeat_at`` (same as renew for Phase 3)."""
        return self.renew_lease(lease, now=now, extension_seconds=extension_seconds)

    def assert_lease(self, lease: JobLease, *, now: datetime) -> LeaseWriteResult:
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        job = self.get_by_id(lease.job_id)
        if lease_is_currently_valid(
            job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        ):
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        return classify_lease_write_after_cas_miss(
            job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        )

    def complete_if_leased(
        self,
        lease: JobLease,
        job: Job,
        *,
        now: datetime,
    ) -> LeaseWriteResult:
        """CAS terminal SUCCEEDED write gated by owner + fencing_token + not-expired lease."""
        if job.id != lease.job_id:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.INVALID_STATE, reason="job_id_mismatch")
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        result_str = json.dumps(job.result_json, ensure_ascii=False) if job.result_json else None
        finalization_meta_str = (
            json.dumps(job.finalization_error_metadata, ensure_ascii=False)
            if job.finalization_error_metadata
            else None
        )
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET status = ?,
                    result_json = ?,
                    error_message = NULL,
                    failure_code = NULL,
                    failure_message = NULL,
                    finalization_error_code = NULL,
                    finalization_error_metadata = ?,
                    updated_at = ?,
                    finished_at = ?,
                    last_heartbeat_at = ?,
                    current_stage = ?,
                    current_substep = ?,
                    prompt_version = ?
                WHERE id = ?
                  AND status IN (?, ?)
                  AND claim_owner_id = ?
                  AND lease_fencing_token = ?
                  AND lease_expires_at >= ?
                """,
                (
                    JobStatus.SUCCEEDED.value,
                    result_str,
                    finalization_meta_str,
                    now_utc,
                    _ensure_utc(job.finished_at) or now_utc,
                    _ensure_utc(job.last_heartbeat_at) or now_utc,
                    job.current_stage,
                    job.current_substep,
                    job.prompt_version,
                    lease.job_id,
                    JobStatus.RUNNING.value,
                    JobStatus.CANCEL_REQUESTED.value,
                    lease.owner_id,
                    lease.fencing_token,
                    now_utc,
                ),
            )
            applied = int(cur.rowcount or 0) == 1
        if applied:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        persisted = self.get_by_id(lease.job_id)
        result = classify_lease_write_after_cas_miss(
            persisted, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        )
        logger.warning(
            "event=job_stale_write_rejected job_id=%s operation=complete owner_id=%s "
            "fencing_token=%s outcome=%s reason=%s",
            lease.job_id,
            lease.owner_id,
            lease.fencing_token,
            result.outcome.value,
            result.reason,
        )
        return result

    def fail_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        error_message: str,
        failure_code: str = "PROCESSING_FAILED",
    ) -> LeaseWriteResult:
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        msg = error_message[:2048] if len(error_message) > 2048 else error_message
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET status = ?,
                    updated_at = ?,
                    finished_at = ?,
                    last_heartbeat_at = ?,
                    failure_code = ?,
                    failure_message = ?,
                    error_message = ?
                WHERE id = ?
                  AND status IN (?, ?)
                  AND claim_owner_id = ?
                  AND lease_fencing_token = ?
                  AND lease_expires_at >= ?
                """,
                (
                    JobStatus.FAILED.value,
                    now_utc,
                    now_utc,
                    now_utc,
                    failure_code,
                    msg,
                    msg,
                    lease.job_id,
                    JobStatus.RUNNING.value,
                    JobStatus.CANCEL_REQUESTED.value,
                    lease.owner_id,
                    lease.fencing_token,
                    now_utc,
                ),
            )
            applied = int(cur.rowcount or 0) == 1
        if applied:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        persisted = self.get_by_id(lease.job_id)
        result = classify_lease_write_after_cas_miss(
            persisted, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        )
        logger.warning(
            "event=job_stale_write_rejected job_id=%s operation=fail owner_id=%s "
            "fencing_token=%s outcome=%s reason=%s",
            lease.job_id,
            lease.owner_id,
            lease.fencing_token,
            result.outcome.value,
            result.reason,
        )
        return result

    def update_finalization_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        mutator,
    ) -> LeaseWriteResult:
        """Apply finalization mutations then persist under lease CAS."""
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        job = self.get_by_id(lease.job_id)
        if not lease_allows_finalization_write(
            job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        ):
            result = classify_lease_write_after_cas_miss(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
            )
            logger.warning(
                "event=job_stale_write_rejected job_id=%s operation=finalization owner_id=%s "
                "fencing_token=%s outcome=%s reason=%s",
                lease.job_id,
                lease.owner_id,
                lease.fencing_token,
                result.outcome.value,
                result.reason,
            )
            return result
        assert job is not None
        mutator(job)
        job.updated_at = now_utc
        finalization_meta_str = (
            json.dumps(job.finalization_error_metadata, ensure_ascii=False)
            if job.finalization_error_metadata
            else None
        )
        result_str = json.dumps(job.result_json, ensure_ascii=False) if job.result_json else None
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET status = ?,
                    result_json = ?,
                    error_message = ?,
                    failure_code = ?,
                    failure_message = ?,
                    updated_at = ?,
                    finished_at = ?,
                    last_heartbeat_at = ?,
                    current_stage = ?,
                    current_substep = ?,
                    finalization_status = ?,
                    current_finalization_step = ?,
                    last_completed_finalization_step = ?,
                    finalization_error_code = ?,
                    finalization_error_metadata = ?,
                    finalization_started_at = ?,
                    finalization_completed_at = ?,
                    domain_persisted_at = ?,
                    artifacts_published_at = ?
                WHERE id = ?
                  AND status IN (?, ?, ?)
                  AND claim_owner_id = ?
                  AND lease_fencing_token = ?
                  AND (
                        status = ?
                     OR (lease_expires_at IS NOT NULL AND lease_expires_at >= ?)
                  )
                """,
                (
                    job.status.value,
                    result_str,
                    job.error_message,
                    job.failure_code,
                    job.failure_message,
                    now_utc,
                    _ensure_utc(job.finished_at),
                    _ensure_utc(job.last_heartbeat_at),
                    job.current_stage,
                    job.current_substep,
                    job.finalization_status.value,
                    job.current_finalization_step.value if job.current_finalization_step else None,
                    job.last_completed_finalization_step.value,
                    job.finalization_error_code,
                    finalization_meta_str,
                    _ensure_utc(job.finalization_started_at),
                    _ensure_utc(job.finalization_completed_at),
                    _ensure_utc(job.domain_persisted_at),
                    _ensure_utc(job.artifacts_published_at),
                    lease.job_id,
                    JobStatus.RUNNING.value,
                    JobStatus.CANCEL_REQUESTED.value,
                    JobStatus.SUCCEEDED.value,
                    lease.owner_id,
                    lease.fencing_token,
                    JobStatus.SUCCEEDED.value,
                    now_utc,
                ),
            )
            applied = int(cur.rowcount or 0) == 1
        if applied:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        persisted = self.get_by_id(lease.job_id)
        result = classify_lease_write_after_cas_miss(
            persisted, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        )
        logger.warning(
            "event=job_stale_write_rejected job_id=%s operation=finalization owner_id=%s "
            "fencing_token=%s outcome=%s reason=%s",
            lease.job_id,
            lease.owner_id,
            lease.fencing_token,
            result.outcome.value,
            result.reason,
        )
        return result

    def acknowledge_cancel_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        reason: str,
    ) -> LeaseWriteResult:
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        msg = reason[:2048] if len(reason) > 2048 else reason
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET status = ?,
                    updated_at = ?,
                    finished_at = ?,
                    last_heartbeat_at = ?,
                    failure_code = ?,
                    failure_message = ?,
                    error_message = ?
                WHERE id = ?
                  AND status IN (?, ?)
                  AND claim_owner_id = ?
                  AND lease_fencing_token = ?
                  AND lease_expires_at >= ?
                """,
                (
                    JobStatus.CANCELED.value,
                    now_utc,
                    now_utc,
                    now_utc,
                    "CANCELED",
                    msg,
                    msg,
                    lease.job_id,
                    JobStatus.RUNNING.value,
                    JobStatus.CANCEL_REQUESTED.value,
                    lease.owner_id,
                    lease.fencing_token,
                    now_utc,
                ),
            )
            applied = int(cur.rowcount or 0) == 1
        if applied:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        persisted = self.get_by_id(lease.job_id)
        result = classify_lease_write_after_cas_miss(
            persisted, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        )
        logger.warning(
            "event=job_stale_write_rejected job_id=%s operation=acknowledge_cancel owner_id=%s "
            "fencing_token=%s outcome=%s reason=%s",
            lease.job_id,
            lease.owner_id,
            lease.fencing_token,
            result.outcome.value,
            result.reason,
        )
        return result

    def try_reclaim_stale_job_and_reconcile_aisle(
        self,
        job_id: str,
        *,
        now: datetime,
        stale_after_seconds: int,
    ) -> StaleReclaimResult:
        if stale_after_seconds <= 0:
            return StaleReclaimResult(won=False, reason="stale_disabled")
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        status_values = tuple(s.value for s in STALE_RECONCILE_STATUSES)
        aisle_applied = False
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            try:
                cur.execute(
                    """
                    UPDATE inventory_jobs
                    SET status = 'failed',
                        updated_at = ?,
                        finished_at = ?,
                        failure_code = ?,
                        failure_message = ?,
                        error_message = ?,
                        finalization_status = CASE
                            WHEN finalization_status IN ('in_progress', 'not_started')
                            THEN 'failed' ELSE finalization_status END,
                        finalization_error_code = CASE
                            WHEN finalization_error_code IS NULL
                                 AND finalization_status IN ('in_progress', 'not_started')
                            THEN ? ELSE finalization_error_code END,
                        finalization_started_at = CASE
                            WHEN finalization_started_at IS NULL
                                 AND finalization_status IN ('in_progress', 'not_started')
                            THEN ? ELSE finalization_started_at END
                    WHERE id = ?
                      AND status IN (?, ?, ?)
                      AND DATEDIFF(SECOND, COALESCE(last_heartbeat_at, updated_at), ?) >= ?
                    """,
                    (
                        now_utc,
                        now_utc,
                        STALE_FAILURE_CODE,
                        STALE_FAILURE_MESSAGE,
                        STALE_FAILURE_MESSAGE,
                        STALE_FAILURE_CODE,
                        now_utc,
                        job_id,
                        *status_values,
                        now_utc,
                        stale_after_seconds,
                    ),
                )
                won = int(cur.rowcount or 0) == 1
                if not won:
                    txn.rollback()
                    return StaleReclaimResult(won=False, reason="cas_lost_or_not_stale")

                cur.execute(
                    """
                    SELECT target_type, target_id, claim_owner_id, attempt_count
                    FROM inventory_jobs WITH (UPDLOCK, ROWLOCK)
                    WHERE id = ?
                    """,
                    (job_id,),
                )
                meta = cur.fetchone()
                target_type = str(getattr(meta, "target_type", None) or meta[0])
                target_id = getattr(meta, "target_id", None)
                if target_id is None:
                    target_id = meta[1]
                claim_owner = getattr(meta, "claim_owner_id", None)
                attempt = getattr(meta, "attempt_count", None)

                if target_type == "aisle" and target_id:
                    cur.execute(
                        """
                        UPDATE aisles WITH (UPDLOCK, HOLDLOCK)
                        SET status = ?,
                            updated_at = ?,
                            error_code = ?,
                            error_message = ?,
                            retryable = 1
                        WHERE id = ?
                          AND status IN (?, ?)
                          AND NOT EXISTS (
                              SELECT 1
                              FROM inventory_jobs j WITH (UPDLOCK, HOLDLOCK)
                              WHERE j.target_type = 'aisle'
                                AND j.target_id = ?
                                AND j.id <> ?
                                AND j.status IN (?, ?, ?)
                          )
                        """,
                        (
                            AisleStatus.FAILED.value,
                            now_utc,
                            STALE_FAILURE_CODE,
                            STALE_FAILURE_MESSAGE,
                            str(target_id),
                            AisleStatus.QUEUED.value,
                            AisleStatus.PROCESSING.value,
                            str(target_id),
                            job_id,
                            *status_values,
                        ),
                    )
                    aisle_applied = int(cur.rowcount or 0) == 1
                    if not aisle_applied:
                        cur.execute(
                            """
                            SELECT TOP 1 id
                            FROM inventory_jobs WITH (UPDLOCK, HOLDLOCK)
                            WHERE target_type = 'aisle'
                              AND target_id = ?
                              AND id <> ?
                              AND status IN (?, ?, ?)
                            """,
                            (str(target_id), job_id, *status_values),
                        )
                        other = cur.fetchone()
                        if other is not None:
                            logger.warning(
                                "event=job_aisle_state_inconsistency job_id=%s aisle_id=%s "
                                "job_status=failed aisle_status=unchanged processing_job_id=%s",
                                job_id,
                                target_id,
                                getattr(other, "id", None) or other[0],
                            )
                txn.commit()
                logger.warning(
                    "event=job_stale_reclaimed job_id=%s aisle_id=%s previous_owner=%s "
                    "new_status=failed attempt=%s",
                    job_id,
                    target_id if target_type == "aisle" else None,
                    claim_owner,
                    attempt,
                )
                return StaleReclaimResult(
                    won=True,
                    job=self.get_by_id(job_id),
                    aisle_transition_applied=aisle_applied,
                    reason="stale_reclaimed",
                )
            except Exception:
                txn.rollback()
                raise
            finally:
                cur.close()

    def reclaim_stale_running_jobs(
        self, stale_after_seconds: int, *, batch_size: int = 100
    ) -> int:
        if stale_after_seconds <= 0:
            return 0
        now_utc = datetime.now(timezone.utc)
        status_values = tuple(s.value for s in STALE_RECONCILE_STATUSES)
        batch = max(1, min(int(batch_size), 500))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT TOP ({batch}) id, target_type, target_id, claim_owner_id,
                       COALESCE(last_heartbeat_at, updated_at) AS hb
                FROM inventory_jobs
                WHERE status IN (?, ?, ?)
                  AND DATEDIFF(SECOND, COALESCE(last_heartbeat_at, updated_at), ?) >= ?
                ORDER BY COALESCE(last_heartbeat_at, updated_at) ASC, id ASC
                """,  # nosec B608
                (*status_values, now_utc, stale_after_seconds),
            )
            rows = list(cur.fetchall() or [])

        reclaimed = 0
        for row in rows:
            job_id = str(getattr(row, "id", None) or row[0])
            logger.warning(
                "event=job_stale_detected job_id=%s aisle_id=%s owner=%s "
                "heartbeat_at=%s stale_threshold=%s",
                job_id,
                getattr(row, "target_id", None),
                getattr(row, "claim_owner_id", None),
                getattr(row, "hb", None),
                stale_after_seconds,
            )
            result = self.try_reclaim_stale_job_and_reconcile_aisle(
                job_id, now=now_utc, stale_after_seconds=stale_after_seconds
            )
            if result.won:
                reclaimed += 1
        return reclaimed
