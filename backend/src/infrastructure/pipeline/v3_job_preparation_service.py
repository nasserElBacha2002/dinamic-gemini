"""
V3 process_aisle job preparation — Phase 6 extraction from :class:`V3JobExecutor`.

Loads job/aisle/assets, applies dispatch gate semantics, and marks STARTING jobs RUNNING.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    JobRepository,
    SourceAssetRepository,
)
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.jobs.worker_bootstrap import append_worker_bootstrap_event, checkpoint_v3_job_bootstrap

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class V3PreparedJob:
    """Gate success: job marked running and ready for pipeline + persistence."""

    job: Job
    aisle: Aisle
    aisle_id: str
    assets: list[Any]


@dataclass(frozen=True)
class V3PreparationResult:
    """Outcome of :meth:`V3JobPreparationService.prepare`.

    When ``stop`` is True, the executor must return ``return_value`` immediately (legacy gate
    semantics: ``False`` for non-v3 jobs, ``True`` for terminal skip / preparation failure).
    When ``stop`` is False, ``prepared`` is set and execution continues.
    """

    stop: bool
    return_value: bool
    prepared: V3PreparedJob | None = None

    @classmethod
    def halt(cls, return_value: bool) -> V3PreparationResult:
        return cls(stop=True, return_value=return_value, prepared=None)

    @classmethod
    def continue_with(cls, prepared: V3PreparedJob) -> V3PreparationResult:
        return cls(stop=False, return_value=False, prepared=prepared)


class V3JobPreparationService:
    """Prepare v3 ``process_aisle`` jobs before pipeline execution."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        source_asset_repo: SourceAssetRepository,
        state_service: V3JobExecutionStateService,
        clock: Clock,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._source_asset_repo = source_asset_repo
        self._state = state_service
        self._clock = clock

    def prepare(self, job_id: str) -> V3PreparationResult:
        """Load job/aisle/assets; halt or return prepared context for pipeline execution."""
        job = self._job_repo.get_by_id(job_id)
        logger.info("v3 dispatch: job_id=%s found=%s", job_id, job is not None)
        if job is None or job.job_type != "process_aisle":
            if job is not None:
                logger.info(
                    "v3 dispatch skipped: job_id=%s job_type=%s target_type=%s target_id=%s",
                    job_id,
                    job.job_type,
                    job.target_type,
                    job.target_id,
                )
            return V3PreparationResult.halt(False)

        logger.info(
            "v3 dispatch accepted: job_id=%s job_type=%s target_type=%s target_id=%s status=%s "
            "configured_identification_mode=%s identification_mode_source=%s "
            "configuration_snapshot_version=%s actual_execution_strategy=%s",
            job_id,
            job.job_type,
            job.target_type,
            job.target_id,
            job.status.value,
            job.identification_mode.value,
            job.identification_mode_source.value,
            job.configuration_snapshot_version,
            job.execution_strategy.value,
        )
        if self._should_skip_for_terminal_job_status(job, job_id):
            return V3PreparationResult.halt(True)

        payload = job.payload_json or {}
        aisle_id = payload.get("aisle_id")
        if not aisle_id:
            self._state.fail_job(job_id, "Missing aisle_id in payload")
            return V3PreparationResult.halt(True)

        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            self._state.fail_job(job_id, f"Aisle not found: {aisle_id}")
            return V3PreparationResult.halt(True)

        logger.info(
            "v3 target resolved: job_id=%s job_type=%s target_type=%s target_id=%s inventory_id=%s aisle_id=%s",
            job_id,
            job.job_type,
            job.target_type,
            job.target_id,
            aisle.inventory_id,
            aisle_id,
        )
        assets = list(self._source_asset_repo.list_by_aisle(aisle_id))
        checkpoint_v3_job_bootstrap(
            job_id=job_id,
            execution_id=job.execution_id,
            substep="executor_bootstrap_completed",
        )
        if not assets:
            self._state.fail_job_and_aisle(job_id, aisle, "No source assets for aisle")
            return V3PreparationResult.halt(True)

        now = self._clock.now()
        logger.info(
            "v3 mark running: job_id=%s job_type=%s target_type=%s target_id=%s inventory_id=%s aisle_id=%s",
            job_id,
            job.job_type,
            job.target_type,
            job.target_id,
            aisle.inventory_id,
            aisle_id,
        )
        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=job.execution_id,
            event="worker.starting_to_running_transition_started",
            details={"inventory_id": aisle.inventory_id, "aisle_id": aisle_id},
        )
        self._state.mark_running(job_id, aisle, now)
        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=job.execution_id,
            event="worker.starting_to_running_transition_completed",
            details={"inventory_id": aisle.inventory_id, "aisle_id": aisle_id},
        )
        return V3PreparationResult.continue_with(
            V3PreparedJob(job=job, aisle=aisle, aisle_id=aisle_id, assets=assets)
        )

    def _should_skip_for_terminal_job_status(self, job: Job, job_id: str) -> bool:
        """True when execute() must return True without running the pipeline body."""
        if job.status == JobStatus.CANCELED:
            logger.info("v3 job %s already canceled, skip", job_id)
            return True
        if job.status == JobStatus.CANCEL_REQUESTED:
            logger.info("v3 job %s cancel requested before start; marking canceled", job_id)
            self._state.cancel_job(job, "Job canceled before execution", now=self._clock.now())
            return True
        if job.status != JobStatus.STARTING:
            logger.warning(
                "v3 job %s invalid status for execution (status=%s), skip", job_id, job.status.value
            )
            return True
        return False
