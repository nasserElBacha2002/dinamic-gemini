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

import pyodbc

from src.application.ports.repositories import JobRepository
from src.application.services.job_claim_helpers import classify_claim_after_cas_miss
from src.application.services.job_stale_reconciler import (
    STALE_FAILURE_CODE,
    STALE_FAILURE_MESSAGE,
    STALE_RECONCILE_STATUSES,
)
from src.database.sqlserver import SqlServerClient
from src.domain.aisle.entities import AisleStatus
from src.domain.aisle_identification.modes import CONFIGURATION_SNAPSHOT_VERSION
from src.domain.jobs.claim import (
    JobClaimOutcome,
    JobClaimResult,
    StaleReclaimResult,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import (
    JobLease,
    LeaseRenewalResult,
    LeaseWriteResult,
)
from src.infrastructure.database.sql_transaction import sql_repository_cursor
from src.infrastructure.repositories.sql_job_lease_store import SqlJobLeaseStore
from src.infrastructure.repositories.sql_job_row_mapper import (
    JOB_SELECT_FIELDS as _JOB_SELECT_FIELDS,
)
from src.infrastructure.repositories.sql_job_row_mapper import (
    ensure_utc as _ensure_utc,
)
from src.infrastructure.repositories.sql_job_row_mapper import (
    parse_json as _parse_json,
)
from src.infrastructure.repositories.sql_job_row_mapper import (
    row_to_job as _row_to_job,
)

logger = logging.getLogger(__name__)

# Max target_ids per SQL ``IN`` clause (parameter-limit safety only — never caps jobs/runs).
TARGET_ID_BATCH_SIZE = 500


def _is_ordered_session_version_unique_violation(exc: BaseException) -> bool:
    """True for unique index ``UQ_inventory_jobs_ordered_session_version`` (2627/2601)."""
    msg = str(exc).lower()
    if "uq_inventory_jobs_ordered_session_version" in msg:
        return True
    args = getattr(exc, "args", ()) or ()
    for item in args:
        blob = str(item).lower()
        if "uq_inventory_jobs_ordered_session_version" in blob:
            return True
        if ("2627" in blob or "2601" in blob) and (
            "ordered_session" in blob or "sequence_version" in blob
        ):
            return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_ordered_session_version_unique_violation(cause)
    return False


class SqlJobRepository(JobRepository):
    def __init__(self, client: SqlServerClient, *, connection: object | None = None) -> None:
        self._client = client
        self._connection = connection
        self._lease_store = SqlJobLeaseStore(client, self.get_by_id)

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
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
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
                    lease_fencing_token = ?, lease_expires_at = ?, lease_acquired_at = ?,
                    ordered_capture_session_id = ?, sequence_version = ?
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
                    job.ordered_capture_session_id,
                    job.sequence_version,
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
                        lease_fencing_token, lease_expires_at, lease_acquired_at,
                        ordered_capture_session_id, sequence_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        job.ordered_capture_session_id,
                        job.sequence_version,
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
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                f"SELECT {_JOB_SELECT_FIELDS} FROM inventory_jobs WHERE id = ?",  # nosec B608
                (job_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_job(row)

    def get_by_ordered_capture_session(
        self, ordered_capture_session_id: str, *, sequence_version: int
    ) -> Job | None:
        session_id = (ordered_capture_session_id or "").strip()
        if not session_id:
            return None
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                f"""
                SELECT {_JOB_SELECT_FIELDS}
                FROM inventory_jobs
                WHERE ordered_capture_session_id = ? AND sequence_version = ?
                """,  # nosec B608
                (session_id, int(sequence_version)),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_job(row)

    def create_or_get_for_ordered_session(self, job: Job) -> tuple[Job, bool]:
        session_id = (job.ordered_capture_session_id or "").strip()
        if not session_id or job.sequence_version is None:
            raise ValueError(
                "create_or_get_for_ordered_session requires "
                "ordered_capture_session_id and sequence_version"
            )
        job.ordered_capture_session_id = session_id
        job.sequence_version = int(job.sequence_version)
        try:
            self.save(job)
            return job, True
        except pyodbc.IntegrityError as exc:
            if not _is_ordered_session_version_unique_violation(exc):
                raise
            existing = self.get_by_ordered_capture_session(
                session_id, sequence_version=int(job.sequence_version)
            )
            if existing is None:
                raise
            return existing, False

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

    def list_jobs_by_retry_of(self, retry_of_job_id: str) -> Sequence[Job]:
        parent = (retry_of_job_id or "").strip()
        if not parent:
            return []
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_JOB_SELECT_FIELDS} FROM inventory_jobs WHERE retry_of_job_id = ?",  # nosec B608
                (parent,),
            )
            rows = cur.fetchall()
        return [_row_to_job(row) for row in rows]

    def list_jobs_for_ops_scan(
        self,
        *,
        limit: int = 200,
        statuses: Sequence[str] | None = None,
    ) -> Sequence[Job]:
        lim = max(1, min(int(limit or 200), 5000))
        status_list = [s.lower() for s in (statuses or []) if s]
        with self._client.cursor() as cur:
            if status_list:
                placeholders = ",".join("?" * len(status_list))
                cur.execute(
                    f"""
                    SELECT TOP ({lim}) {_JOB_SELECT_FIELDS}
                    FROM inventory_jobs
                    WHERE status IN ({placeholders})
                    ORDER BY updated_at DESC, created_at DESC
                    """,  # nosec B608
                    tuple(status_list),
                )
            else:
                cur.execute(
                    f"""
                    SELECT TOP ({lim}) {_JOB_SELECT_FIELDS}
                    FROM inventory_jobs
                    ORDER BY updated_at DESC, created_at DESC
                    """  # nosec B608
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
        return self._lease_store.renew_lease(
            lease, now=now, extension_seconds=extension_seconds
        )

    def reacquire_expired_lease(
        self,
        job_id: str,
        *,
        now: datetime,
        new_owner_id: str,
        extension_seconds: int,
    ) -> JobClaimResult:
        return self._lease_store.reacquire_expired_lease(
            job_id,
            now=now,
            new_owner_id=new_owner_id,
            extension_seconds=extension_seconds,
        )

    def merge_result_json_if_leased(
        self,
        lease: JobLease,
        patch: dict[str, Any],
        *,
        now: datetime,
    ) -> tuple[LeaseWriteResult, Job | None]:
        return self._lease_store.merge_result_json_if_leased(lease, patch, now=now)

    def touch_heartbeat_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        return self._lease_store.touch_heartbeat_if_leased(
            lease, now=now, extension_seconds=extension_seconds
        )

    def assert_lease(self, lease: JobLease, *, now: datetime) -> LeaseWriteResult:
        return self._lease_store.assert_lease(lease, now=now)

    def complete_if_leased(
        self,
        lease: JobLease,
        job: Job,
        *,
        now: datetime,
    ) -> LeaseWriteResult:
        return self._lease_store.complete_if_leased(lease, job, now=now)

    def fail_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        error_message: str,
        failure_code: str = "PROCESSING_FAILED",
    ) -> LeaseWriteResult:
        return self._lease_store.fail_if_leased(
            lease,
            now=now,
            error_message=error_message,
            failure_code=failure_code,
        )

    def update_finalization_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        mutator,
    ) -> LeaseWriteResult:
        return self._lease_store.update_finalization_if_leased(
            lease, now=now, mutator=mutator
        )

    def acknowledge_cancel_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        reason: str,
    ) -> LeaseWriteResult:
        return self._lease_store.acknowledge_cancel_if_leased(
            lease, now=now, reason=reason
        )

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
