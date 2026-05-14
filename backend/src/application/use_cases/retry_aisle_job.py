from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from src.application.errors import ActiveJobExistsError
from src.application.ports.contracts import ProcessAislePayload
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.process_aisle_job_for_aisle import (
    require_process_aisle_job_for_aisle,
)
from src.domain.jobs.entities import Job, JobStatus
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE

logger = logging.getLogger(__name__)

# Phase 7 retry lineage semantics:
# - retry_of_job_id always points to the immediate previous attempt
# - retries form one linear chain per aisle processing flow
# - only the latest retryable terminal attempt may be retried
RETRYABLE_JOB_STATUSES = (JobStatus.FAILED, JobStatus.CANCELED)
NON_RETRYABLE_JOB_STATUSES = (
    JobStatus.QUEUED,
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
    JobStatus.SUCCEEDED,
)


def _assert_job_retryable(original_job: Job, job_id: str) -> None:
    if original_job.status not in RETRYABLE_JOB_STATUSES:
        raise ValueError(f"Cannot retry job {job_id} with status {original_job.status.value!r}")


def _assert_may_retry_as_latest_terminal_attempt(
    *,
    stale_reconciler: JobStaleReconciler,
    job_repo: JobRepository,
    aisle_id: str,
    original_job: Job,
    job_id: str,
) -> None:
    latest = stale_reconciler.reconcile(job_repo.get_latest_by_target("aisle", aisle_id))
    if latest is not None and latest.status in NON_RETRYABLE_JOB_STATUSES:
        raise ActiveJobExistsError(
            f"Aisle {aisle_id} already has an active job (status={latest.status.value})"
        )
    if latest is not None and latest.id != original_job.id:
        raise ValueError(
            f"Cannot retry job {job_id}: latest retryable terminal attempt is {latest.id}"
        )


@dataclass
class RetryAisleJobCommand:
    inventory_id: str
    aisle_id: str
    job_id: str


class RetryAisleJobUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        launch_service: AisleJobLaunchService,
        stale_reconciler: JobStaleReconciler,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._launch_service = launch_service
        self._stale_reconciler = stale_reconciler

    def execute(self, command: RetryAisleJobCommand) -> Job:
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="merged",
        )

        original_job = require_process_aisle_job_for_aisle(
            self._job_repo,
            job_id=command.job_id,
            aisle_id=command.aisle_id,
        )
        _assert_job_retryable(original_job, command.job_id)
        _assert_may_retry_as_latest_terminal_attempt(
            stale_reconciler=self._stale_reconciler,
            job_repo=self._job_repo,
            aisle_id=command.aisle_id,
            original_job=original_job,
            job_id=command.job_id,
        )

        raw_payload = dict(original_job.payload_json or {})
        aisle_from_job = raw_payload.get("aisle_id")
        resolved_aisle_id = (
            aisle_from_job.strip()
            if isinstance(aisle_from_job, str) and aisle_from_job.strip()
            else aisle.id
        )
        raw_payload["aisle_id"] = resolved_aisle_id
        payload = cast(ProcessAislePayload, raw_payload)
        retry_job = self._launch_service.create_and_launch_attempt(
            aisle=aisle,
            payload=payload,
            attempt_count=int(original_job.attempt_count or 1) + 1,
            retry_of_job_id=original_job.id,
            log_prefix="job.retry_requested",
            provider_name=(original_job.provider_name or "gemini").strip().lower(),
            model_name=original_job.model_name,
            prompt_key=(original_job.prompt_key or DEFAULT_HYBRID_PROMPT_PROFILE),
        )
        logger.info(
            "job.retry_requested previous_job_id=%s new_job_id=%s aisle_id=%s attempt_count=%s",
            original_job.id,
            retry_job.id,
            command.aisle_id,
            retry_job.attempt_count,
        )
        return retry_job
