"""Phase 5 — recover a stale job by stale-fail + new attempt (idempotent)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, cast

from src.application.errors import WorkerLaunchFailedError
from src.application.ports.clock import Clock
from src.application.ports.contracts import ProcessAislePayload
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.sql_contention_classifier import (
    is_transient_sql_contention,
    is_unique_retry_of_violation,
)
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job, JobStatus
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE
from src.observability.logging import log_event
from src.observability.metrics.instruments import record_job_outcome
from src.observability.request_ids import generate_correlation_id, normalize_inbound_id

logger = logging.getLogger(__name__)

CORRELATION_PAYLOAD_KEY = "correlation_id"
WORKER_LAUNCH_FAILED_CODE = WorkerLaunchFailedError.failure_code


class RecoverStaleJobOutcome(str, Enum):
    RECOVERED = "RECOVERED"
    RELAUNCHED = "RELAUNCHED"
    RELAUNCH_FAILED = "RELAUNCH_FAILED"
    CHILD_TERMINAL = "CHILD_TERMINAL"
    DRY_RUN = "DRY_RUN"
    ACTIVE_LEASE = "ACTIVE_LEASE"
    NOT_STALE = "NOT_STALE"
    MAX_ATTEMPTS = "MAX_ATTEMPTS"
    ALREADY_RECOVERED = "ALREADY_RECOVERED"
    LOST_CAS = "LOST_CAS"
    RETRY_CREATE_FAILED = "RETRY_CREATE_FAILED"
    WORKER_LAUNCH_FAILED = "WORKER_LAUNCH_FAILED"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED_TARGET = "UNSUPPORTED_TARGET"
    CHILD_INCONSISTENT = "CHILD_INCONSISTENT"


class ChildRecoveryState(str, Enum):
    CHILD_ACTIVE = "CHILD_ACTIVE"
    CHILD_SUCCEEDED = "CHILD_SUCCEEDED"
    CHILD_LAUNCH_FAILED = "CHILD_LAUNCH_FAILED"
    CHILD_TERMINAL_FUNCTIONAL_FAILURE = "CHILD_TERMINAL_FUNCTIONAL_FAILURE"
    CHILD_INCONSISTENT = "CHILD_INCONSISTENT"


@dataclass(frozen=True, slots=True)
class RecoverStaleJobResult:
    outcome: RecoverStaleJobOutcome
    job_id: str
    new_job_id: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class RecoverStaleJobCommand:
    job_id: str
    actor: str
    reason: str
    dry_run: bool = True
    stale_after_seconds: int = 900
    max_attempts: int = 3


def job_correlation_id(job: Job) -> str:
    raw = None
    if isinstance(job.payload_json, dict):
        raw = job.payload_json.get(CORRELATION_PAYLOAD_KEY)
    if isinstance(raw, str) and raw.strip():
        return normalize_inbound_id(raw, fallback=generate_correlation_id())
    return generate_correlation_id()


def ensure_payload_correlation(payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    out = dict(payload)
    out[CORRELATION_PAYLOAD_KEY] = correlation_id
    return out


def classify_child_recovery_state(child: Job) -> ChildRecoveryState:
    """Map an existing retry child to a recovery action class."""
    status = child.status
    failure = (child.failure_code or "").strip()

    if status in (
        JobStatus.QUEUED,
        JobStatus.STARTING,
        JobStatus.RUNNING,
        JobStatus.CANCEL_REQUESTED,
    ):
        return ChildRecoveryState.CHILD_ACTIVE
    if status == JobStatus.SUCCEEDED:
        return ChildRecoveryState.CHILD_SUCCEEDED
    if status == JobStatus.FAILED and failure == WORKER_LAUNCH_FAILED_CODE:
        return ChildRecoveryState.CHILD_LAUNCH_FAILED
    if status in (JobStatus.FAILED, JobStatus.CANCELED):
        return ChildRecoveryState.CHILD_TERMINAL_FUNCTIONAL_FAILURE
    return ChildRecoveryState.CHILD_INCONSISTENT


def _find_child_retry(job_repo: JobRepository, parent_job_id: str) -> Job | None:
    children = list(job_repo.list_jobs_by_retry_of(parent_job_id))
    if not children:
        return None
    if len(children) > 1:
        # Unique index should prevent this; pick newest for classification diagnostics.
        children = sorted(children, key=lambda j: j.created_at, reverse=True)
    return children[0]


def _has_active_lease(job: Job, *, now: datetime) -> bool:
    if job.status not in (
        JobStatus.RUNNING,
        JobStatus.STARTING,
        JobStatus.CANCEL_REQUESTED,
    ):
        return False
    if not (job.claim_owner_id or "").strip():
        return False
    exp = job.lease_expires_at
    if exp is None:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp >= now


def _is_stale_candidate(job: Job, *, now: datetime, stale_after_seconds: int) -> bool:
    if job.status not in (
        JobStatus.RUNNING,
        JobStatus.STARTING,
        JobStatus.CANCEL_REQUESTED,
    ):
        return False
    reference = job.last_heartbeat_at or job.updated_at
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return (now - reference).total_seconds() >= stale_after_seconds


@dataclass
class RecoverStaleJobUseCase:
    job_repo: JobRepository
    aisle_repo: AisleRepository
    launch_service: AisleJobLaunchService
    clock: Clock

    def execute(self, command: RecoverStaleJobCommand) -> RecoverStaleJobResult:
        now = self.clock.now()
        job = self.job_repo.get_by_id(command.job_id)
        if job is None:
            return RecoverStaleJobResult(RecoverStaleJobOutcome.NOT_FOUND, command.job_id)

        if job.target_type != "aisle":
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.UNSUPPORTED_TARGET,
                job.id,
                detail="only aisle process jobs are supported",
            )

        aisle = self.aisle_repo.get_by_id(job.target_id)
        if aisle is None:
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.NOT_FOUND,
                job.id,
                detail="aisle_not_found",
            )

        existing_child = _find_child_retry(self.job_repo, job.id)
        if existing_child is not None:
            return self._handle_existing_child(
                parent=job,
                child=existing_child,
                command=command,
            )

        if _has_active_lease(job, now=now):
            log_event(
                "job_recovery_refused",
                component="recovery",
                operation="recover_stale_job",
                outcome="active_lease",
                job_id=job.id,
                actor=command.actor,
                reason_code="ACTIVE_LEASE",
            )
            return RecoverStaleJobResult(RecoverStaleJobOutcome.ACTIVE_LEASE, job.id)

        if job.status == JobStatus.FAILED and (job.failure_code or "") == "STALE_JOB":
            pass
        elif not _is_stale_candidate(
            job, now=now, stale_after_seconds=command.stale_after_seconds
        ):
            return RecoverStaleJobResult(RecoverStaleJobOutcome.NOT_STALE, job.id)

        if int(job.attempt_count or 1) >= int(command.max_attempts):
            return RecoverStaleJobResult(RecoverStaleJobOutcome.MAX_ATTEMPTS, job.id)

        if command.dry_run:
            log_event(
                "job_recovery_started",
                component="recovery",
                operation="recover_stale_job",
                outcome="dry_run",
                job_id=job.id,
                actor=command.actor,
                reason_code=command.reason,
            )
            return RecoverStaleJobResult(RecoverStaleJobOutcome.DRY_RUN, job.id)

        log_event(
            "job_recovery_started",
            component="recovery",
            operation="recover_stale_job",
            outcome="started",
            job_id=job.id,
            actor=command.actor,
            reason_code=command.reason,
        )

        job = self.job_repo.get_by_id(command.job_id) or job
        existing_child = _find_child_retry(self.job_repo, job.id)
        if existing_child is not None:
            return self._handle_existing_child(
                parent=job,
                child=existing_child,
                command=command,
            )

        if job.status != JobStatus.FAILED:
            try:
                reclaim = self.job_repo.try_reclaim_stale_job_and_reconcile_aisle(
                    job.id,
                    now=now,
                    stale_after_seconds=command.stale_after_seconds,
                )
            except Exception as exc:
                if is_transient_sql_contention(exc):
                    logger.warning(
                        "recover_stale_job reclaim contention job_id=%s", job.id, exc_info=True
                    )
                    return RecoverStaleJobResult(
                        RecoverStaleJobOutcome.LOST_CAS, job.id, detail="sql_contention"
                    )
                raise
            if not reclaim.won:
                child = _find_child_retry(self.job_repo, job.id)
                if child is not None:
                    return self._handle_existing_child(
                        parent=job, child=child, command=command
                    )
                return RecoverStaleJobResult(RecoverStaleJobOutcome.LOST_CAS, job.id)
            job = reclaim.job or self.job_repo.get_by_id(job.id) or job
            record_job_outcome(job_type=job.job_type or "process_aisle", outcome="stale")
        elif (job.failure_code or "") != "STALE_JOB":
            return RecoverStaleJobResult(RecoverStaleJobOutcome.NOT_STALE, job.id)

        child = _find_child_retry(self.job_repo, job.id)
        if child is not None:
            return self._handle_existing_child(parent=job, child=child, command=command)

        correlation = job_correlation_id(job)
        raw_payload = ensure_payload_correlation(dict(job.payload_json or {}), correlation)
        aisle_from_job = raw_payload.get("aisle_id")
        resolved_aisle_id = (
            aisle_from_job.strip()
            if isinstance(aisle_from_job, str) and aisle_from_job.strip()
            else aisle.id
        )
        raw_payload["aisle_id"] = resolved_aisle_id
        payload = cast(ProcessAislePayload, raw_payload)

        try:
            new_job = self._create_retry_attempt(
                aisle=aisle,
                original=job,
                payload=payload,
            )
        except WorkerLaunchFailedError as exc:
            child = _find_child_retry(self.job_repo, job.id)
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.WORKER_LAUNCH_FAILED,
                job.id,
                new_job_id=child.id if child else exc.job_id,
                detail=str(exc),
            )
        except Exception as exc:
            logger.exception("recover_stale_job retry create failed job_id=%s", job.id)
            log_event(
                "job_recovery_failed",
                component="recovery",
                operation="recover_stale_job",
                outcome="retry_create_failed",
                job_id=job.id,
                reason_code=type(exc).__name__,
                actor=command.actor,
            )
            child = _find_child_retry(self.job_repo, job.id)
            if child is not None or is_unique_retry_of_violation(exc):
                if child is None:
                    child = _find_child_retry(self.job_repo, job.id)
                if child is not None:
                    return self._handle_existing_child(
                        parent=job, child=child, command=command
                    )
                return RecoverStaleJobResult(
                    RecoverStaleJobOutcome.ALREADY_RECOVERED,
                    job.id,
                    detail=str(exc),
                )
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.RETRY_CREATE_FAILED,
                job.id,
                detail=str(exc),
            )

        record_job_outcome(job_type=new_job.job_type or "process_aisle", outcome="recovered")
        log_event(
            "job_recovery_completed",
            component="recovery",
            operation="recover_stale_job",
            outcome="recovered",
            job_id=job.id,
            new_job_id=new_job.id,
            actor=command.actor,
            reason_code=command.reason,
            correlation_id=correlation,
        )
        return RecoverStaleJobResult(
            RecoverStaleJobOutcome.RECOVERED,
            job.id,
            new_job_id=new_job.id,
        )

    def _handle_existing_child(
        self,
        *,
        parent: Job,
        child: Job,
        command: RecoverStaleJobCommand,
    ) -> RecoverStaleJobResult:
        state = classify_child_recovery_state(child)
        if state == ChildRecoveryState.CHILD_ACTIVE:
            log_event(
                "job_recovery_completed",
                component="recovery",
                operation="recover_stale_job",
                outcome="already_recovered",
                job_id=parent.id,
                new_job_id=child.id,
                actor=command.actor,
                reason_code="CHILD_ACTIVE",
            )
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.ALREADY_RECOVERED,
                parent.id,
                new_job_id=child.id,
                detail=state.value,
            )
        if state == ChildRecoveryState.CHILD_SUCCEEDED:
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.ALREADY_RECOVERED,
                parent.id,
                new_job_id=child.id,
                detail=state.value,
            )
        if state == ChildRecoveryState.CHILD_TERMINAL_FUNCTIONAL_FAILURE:
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.CHILD_TERMINAL,
                parent.id,
                new_job_id=child.id,
                detail=state.value,
            )
        if state == ChildRecoveryState.CHILD_INCONSISTENT:
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.CHILD_INCONSISTENT,
                parent.id,
                new_job_id=child.id,
                detail=state.value,
            )
        # CHILD_LAUNCH_FAILED — idempotent relaunch of the same child (no second child).
        if command.dry_run:
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.DRY_RUN,
                parent.id,
                new_job_id=child.id,
                detail="would_relaunch_child",
            )
        try:
            execution_id = self.launch_service.relaunch_failed_worker(
                child,
                idempotency_key=f"recovery-relaunch:{child.id}",
            )
        except WorkerLaunchFailedError as exc:
            return RecoverStaleJobResult(
                RecoverStaleJobOutcome.RELAUNCH_FAILED,
                parent.id,
                new_job_id=child.id,
                detail=str(exc),
            )
        log_event(
            "job_recovery_completed",
            component="recovery",
            operation="recover_stale_job",
            outcome="relaunched",
            job_id=parent.id,
            new_job_id=child.id,
            actor=command.actor,
            reason_code=command.reason,
            execution_id=execution_id,
        )
        record_job_outcome(job_type=child.job_type or "process_aisle", outcome="recovered")
        return RecoverStaleJobResult(
            RecoverStaleJobOutcome.RELAUNCHED,
            parent.id,
            new_job_id=child.id,
            detail=execution_id,
        )

    def _create_retry_attempt(
        self,
        *,
        aisle: Aisle,
        original: Job,
        payload: ProcessAislePayload,
    ) -> Job:
        return self.launch_service.create_and_launch_attempt(
            aisle=aisle,
            payload=payload,
            attempt_count=int(original.attempt_count or 1) + 1,
            retry_of_job_id=original.id,
            log_prefix="job.recovery_requested",
            provider_name=(original.provider_name or "gemini").strip().lower(),
            model_name=original.model_name,
            prompt_key=DEFAULT_HYBRID_PROMPT_PROFILE,
            identification_mode=original.identification_mode,
            identification_mode_source=original.identification_mode_source,
            configuration_snapshot_version=original.configuration_snapshot_version,
            execution_strategy=original.execution_strategy,
            engine_params_json=(
                dict(original.engine_params_json)
                if isinstance(original.engine_params_json, dict)
                else None
            ),
        )
