"""
StartAisleProcessing use case — v3.0 (Épica 4).

Creates a processing job for an aisle and enqueues it. Fails if aisle does not exist,
aisle does not belong to the given inventory, or an active job already exists for the aisle.

Phase 9: when ``resolve_execution_keys`` is true (HTTP entry), loads inventory and resolves
provider/model/prompt via ``resolve_process_aisle_execution_keys`` before launch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.application.errors import AisleNotFoundError, ActiveJobExistsError, InventoryNotFoundError
from src.application.ports.contracts import ProcessAislePayload
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.process_aisle_execution_resolution import (
    resolve_process_aisle_execution_keys,
)
from src.config import load_settings
from src.domain.jobs.entities import Job, JobStatus

logger = logging.getLogger(__name__)


@dataclass
class StartAisleProcessingCommand:
    inventory_id: str
    aisle_id: str
    #: When true (API route), load inventory and resolve execution keys from inventory + requests.
    resolve_execution_keys: bool = False
    requested_provider_name: Optional[str] = None
    requested_model_name: Optional[str] = None
    requested_prompt_key: Optional[str] = None
    #: Used only when ``resolve_execution_keys`` is false (e.g. unit tests with pre-resolved keys).
    pipeline_provider_key: str = "gemini"
    model_name: Optional[str] = None
    prompt_key: str = "global_v21"


class StartAisleProcessingUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        launch_service: AisleJobLaunchService,
        stale_reconciler: JobStaleReconciler,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._launch_service = launch_service
        self._stale_reconciler = stale_reconciler

    def execute(self, command: StartAisleProcessingCommand) -> str:
        if command.resolve_execution_keys:
            inv = self._inventory_repo.get_by_id(command.inventory_id)
            if inv is None:
                raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
            settings = load_settings()
            pipeline_key, model_name, prompt_key = resolve_process_aisle_execution_keys(
                inv,
                requested_provider_name=command.requested_provider_name,
                requested_model_name=command.requested_model_name,
                requested_prompt_key=command.requested_prompt_key,
                settings=settings,
            )
            logger.info(
                "aisle.process_requested inventory_id=%s aisle_id=%s processing_mode=%s provider=%s",
                command.inventory_id,
                command.aisle_id,
                inv.processing_mode.value,
                pipeline_key,
            )
        else:
            pipeline_key = command.pipeline_provider_key
            model_name = command.model_name
            prompt_key = command.prompt_key

        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {command.aisle_id}")
        if aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )

        latest = self._stale_reconciler.reconcile(
            self._job_repo.get_latest_by_target("aisle", command.aisle_id)
        )
        if latest is not None and latest.status in (
            JobStatus.QUEUED,
            JobStatus.STARTING,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ):
            raise ActiveJobExistsError(
                f"Aisle {command.aisle_id} already has an active job (status={latest.status.value})"
            )

        payload: ProcessAislePayload = {"aisle_id": command.aisle_id}
        job = self._launch_service.create_and_launch_attempt(
            aisle=aisle,
            payload=payload,
            attempt_count=1,
            retry_of_job_id=None,
            log_prefix="job.start_requested",
            provider_name=pipeline_key,
            model_name=model_name,
            prompt_key=prompt_key,
        )
        return job.id
