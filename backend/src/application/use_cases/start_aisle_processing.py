"""
StartAisleProcessing use case — v3.0 (Épica 4).

Creates a processing job for an aisle and enqueues it. Fails if aisle does not exist,
aisle does not belong to the given inventory, or an active job already exists for the aisle.

Phase 9: when ``resolve_execution_keys`` is true (HTTP entry), loads inventory and resolves
provider/model/prompt via ``resolve_process_aisle_execution_keys`` before launch.

Phase 10: execution-key materialization and aisle scope checks are factored into small helpers
for readability; behavior is unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.errors import (
    ActiveJobExistsError,
    InventoryNotFoundError,
    NoSourceAssetsForAisleProcessingError,
)
from src.application.ports.contracts import ProcessAislePayload
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    SourceAssetRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.process_aisle_execution_resolution import (
    resolve_process_aisle_execution_keys,
)
from src.config import load_settings
from src.domain.jobs.entities import JobStatus
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE

logger = logging.getLogger(__name__)

_START_BLOCKING_JOB_STATUSES = (
    JobStatus.QUEUED,
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
)


def _require_no_active_process_job_for_aisle(
    *,
    stale_reconciler: JobStaleReconciler,
    job_repo: JobRepository,
    aisle_id: str,
) -> None:
    """Raise if an aisle-target job is already in a state that blocks a new start."""
    latest = stale_reconciler.reconcile(job_repo.get_latest_by_target("aisle", aisle_id))
    if latest is not None and latest.status in _START_BLOCKING_JOB_STATUSES:
        raise ActiveJobExistsError(
            f"Aisle {aisle_id} already has an active job (status={latest.status.value})"
        )


@dataclass
class StartAisleProcessingCommand:
    inventory_id: str
    aisle_id: str
    #: When true (API route), load inventory and resolve execution keys from inventory + requests.
    resolve_execution_keys: bool = False
    requested_provider_name: str | None = None
    requested_model_name: str | None = None
    requested_prompt_key: str | None = None
    #: Used only when ``resolve_execution_keys`` is false (e.g. unit tests with pre-resolved keys).
    pipeline_provider_key: str = "gemini"
    model_name: str | None = None
    prompt_key: str = DEFAULT_HYBRID_PROMPT_PROFILE


def _materialize_execution_keys_for_start(
    inventory_repo: InventoryRepository,
    command: StartAisleProcessingCommand,
) -> tuple[str, str | None, str]:
    """Resolve provider/model/prompt for a start-process command (Phase 9/10).

    When ``command.resolve_execution_keys`` is false, returns the command's pre-set keys.
    """
    if not command.resolve_execution_keys:
        return (
            command.pipeline_provider_key,
            command.model_name,
            command.prompt_key,
        )
    inv = inventory_repo.get_by_id(command.inventory_id)
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
    return pipeline_key, model_name, prompt_key


class StartAisleProcessingUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        job_repo: JobRepository,
        launch_service: AisleJobLaunchService,
        stale_reconciler: JobStaleReconciler,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._job_repo = job_repo
        self._launch_service = launch_service
        self._stale_reconciler = stale_reconciler

    def execute(self, command: StartAisleProcessingCommand) -> str:
        pipeline_key, model_name, _resolved_prompt = _materialize_execution_keys_for_start(
            self._inventory_repo,
            command,
        )
        # Product policy: all new aisle jobs persist the label-first hybrid profile key.
        prompt_key = DEFAULT_HYBRID_PROMPT_PROFILE
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )

        aisle_assets = self._asset_repo.list_by_aisle(command.aisle_id)
        if not aisle_assets:
            logger.info(
                "aisle.process_rejected_no_source_assets inventory_id=%s aisle_id=%s",
                command.inventory_id,
                command.aisle_id,
            )
            raise NoSourceAssetsForAisleProcessingError(
                f"No source assets for aisle {command.aisle_id}; upload media before processing."
            )

        _require_no_active_process_job_for_aisle(
            stale_reconciler=self._stale_reconciler,
            job_repo=self._job_repo,
            aisle_id=command.aisle_id,
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
