"""Phase 7 — reprocess / invalidate asset mutations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from src.application.errors import (
    AssetNotInJobSnapshotError,
    AssetProcessingStateConcurrencyError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    ProcessingObservabilityDisabledError,
    SourceAssetNotFoundForAisleError,
    StrategyDisabledError,
)
from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.processing_event_repository import ProcessingEventRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.config import load_settings
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_event import ProcessingEvent

logger = logging.getLogger(__name__)


@dataclass
class ReprocessAssetCommand:
    inventory_id: str
    aisle_id: str
    job_id: str
    asset_id: str
    reason: str
    expected_state_version: int
    strategy: str | None = None
    manual_policy: str | None = None
    idempotency_key: str | None = None
    actor: str | None = None


@dataclass
class InvalidateAssetResultCommand:
    inventory_id: str
    aisle_id: str
    job_id: str
    asset_id: str
    reason: str
    expected_state_version: int
    idempotency_key: str | None = None
    actor: str | None = None


class ReprocessAssetUseCase:
    """Queue a same-job per-asset reprocess without wiping attempt history.

    Resets ``job_asset_processing_states`` to PENDING (optimistic version check).
    Actual strategy execution is picked up by the running job worker when the job
    is still active, or left PENDING for a follow-up single-asset runner.
    """

    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        state_repo: JobAssetProcessingStateRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        clock: Clock,
        event_repo: ProcessingEventRepository | None = None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._state_repo = state_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._clock = clock
        self._event_repo = event_repo
        self._seen_idempotency: set[str] = set()

    def execute(self, command: ReprocessAssetCommand) -> dict:
        settings = load_settings()
        if not bool(getattr(settings, "processing_observability_enabled", False)):
            raise ProcessingObservabilityDisabledError("PROCESSING_OBSERVABILITY_ENABLED=false")
        if not bool(getattr(settings, "processing_asset_reprocess_enabled", False)):
            raise StrategyDisabledError("PROCESSING_ASSET_REPROCESS_ENABLED=false")

        if command.idempotency_key:
            key = f"reprocess|{command.job_id}|{command.asset_id}|{command.idempotency_key}"
            if key in self._seen_idempotency:
                state = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
                return {
                    "asset_id": command.asset_id,
                    "state_version": state.version if state else command.expected_state_version,
                    "status": state.status.value if state else "PENDING",
                    "idempotent_replay": True,
                }
            self._seen_idempotency.add(key)

        job = self._load_job(command.inventory_id, command.aisle_id, command.job_id)
        self._ensure_asset_in_snapshot(command.job_id, command.asset_id)

        state = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
        if state is None:
            raise AssetNotInJobSnapshotError(
                f"No processing state for asset {command.asset_id} on job {command.job_id}"
            )
        if state.version != command.expected_state_version:
            raise AssetProcessingStateConcurrencyError("ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT")
        if state.status is JobAssetProcessingStatus.PROCESSING:
            raise AssetProcessingStateConcurrencyError(
                "ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT"
            )

        strategy = (command.strategy or state.last_strategy or "AUTO").strip().upper()
        if strategy == "EXTERNAL_PROVIDER" and not bool(
            getattr(settings, "external_fallback_per_image_enabled", False)
        ):
            raise StrategyDisabledError("EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=false")

        now = self._clock.now()
        state.status = JobAssetProcessingStatus.PENDING
        state.last_strategy = None if strategy == "AUTO" else strategy
        state.error_code = None
        state.error_message = None
        state.worker_token = None
        state.lease_expires_at = None
        state.started_at = None
        state.finished_at = None
        state.updated_at = now
        state.version = int(command.expected_state_version) + 1
        # Keep active_result_id for history; new success path reconciles via persister.
        try:
            self._state_repo.save_with_ownership(
                state,
                expected_version=command.expected_state_version,
                worker_token=None,
            )
        except AssetProcessingStateConcurrencyError:
            raise

        refreshed = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
        self._emit(
            job_id=command.job_id,
            asset_id=command.asset_id,
            event_type="asset.reprocess_queued",
            message=f"Reprocess queued ({command.reason})",
            strategy=strategy,
            metadata={
                "reason": command.reason,
                "manual_policy": command.manual_policy,
                "actor": command.actor,
                "job_status": getattr(job.status, "value", str(job.status)),
            },
        )
        logger.info(
            "processing_ui.reprocess_requested job_id=%s asset_id=%s strategy=%s",
            command.job_id,
            command.asset_id,
            strategy,
        )
        return {
            "asset_id": command.asset_id,
            "state_version": refreshed.version if refreshed else state.version + 1,
            "status": refreshed.status.value if refreshed else "PENDING",
        }

    def _emit(self, **kwargs) -> None:
        if self._event_repo is None:
            return
        settings = load_settings()
        if not bool(getattr(settings, "processing_events_persistence_enabled", False)):
            return
        now = self._clock.now()
        self._event_repo.append(
            ProcessingEvent(
                id=str(uuid4()),
                job_id=kwargs["job_id"],
                asset_id=kwargs.get("asset_id"),
                event_type=kwargs["event_type"],
                created_at=now,
                strategy=kwargs.get("strategy"),
                message=kwargs.get("message"),
                metadata=kwargs.get("metadata") or {},
            )
        )

    def _load_job(self, inventory_id: str, aisle_id: str, job_id: str):
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo, aisle_id=aisle_id, inventory_id=inventory_id
        )
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_id != aisle.id:
            raise JobDoesNotBelongToAisleError(
                f"Job {job_id} does not belong to aisle {aisle_id}"
            )
        return job

    def _ensure_asset_in_snapshot(self, job_id: str, asset_id: str) -> None:
        links = self._job_source_asset_repo.list_by_job(job_id)
        if not any(link.source_asset_id == asset_id for link in links):
            raise AssetNotInJobSnapshotError(
                f"Asset {asset_id} is not part of job snapshot {job_id}"
            )


class InvalidateAssetResultUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        state_repo: JobAssetProcessingStateRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        clock: Clock,
        event_repo: ProcessingEventRepository | None = None,
    ) -> None:
        self._reprocess_deps = ReprocessAssetUseCase(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            state_repo=state_repo,
            job_source_asset_repo=job_source_asset_repo,
            clock=clock,
            event_repo=event_repo,
        )
        self._state_repo = state_repo
        self._clock = clock
        self._event_repo = event_repo
        self._seen_idempotency: set[str] = set()

    def execute(self, command: InvalidateAssetResultCommand) -> dict:
        settings = load_settings()
        if not bool(getattr(settings, "processing_observability_enabled", False)):
            raise ProcessingObservabilityDisabledError("PROCESSING_OBSERVABILITY_ENABLED=false")
        if not bool(getattr(settings, "processing_manual_actions_enabled", False)):
            raise StrategyDisabledError("PROCESSING_MANUAL_ACTIONS_ENABLED=false")

        if command.idempotency_key:
            key = f"invalidate|{command.job_id}|{command.asset_id}|{command.idempotency_key}"
            if key in self._seen_idempotency:
                state = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
                return {
                    "asset_id": command.asset_id,
                    "state_version": state.version if state else command.expected_state_version,
                    "status": state.status.value if state else "PENDING_MANUAL_REVIEW",
                    "idempotent_replay": True,
                }
            self._seen_idempotency.add(key)

        self._reprocess_deps._load_job(
            command.inventory_id, command.aisle_id, command.job_id
        )
        self._reprocess_deps._ensure_asset_in_snapshot(command.job_id, command.asset_id)
        state = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
        if state is None:
            raise SourceAssetNotFoundForAisleError(
                f"No processing state for asset {command.asset_id}"
            )
        if state.version != command.expected_state_version:
            raise AssetProcessingStateConcurrencyError("ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT")
        if state.status is JobAssetProcessingStatus.PROCESSING:
            raise AssetProcessingStateConcurrencyError(
                "ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT"
            )

        prior_active = state.active_result_id
        now = self._clock.now()
        state.status = JobAssetProcessingStatus.PENDING_MANUAL_REVIEW
        state.active_result_id = None
        state.error_code = "RESULT_INVALIDATED"
        state.error_message = (command.reason or "")[:500]
        state.updated_at = now
        state.version = int(command.expected_state_version) + 1
        self._state_repo.save_with_ownership(
            state,
            expected_version=command.expected_state_version,
            worker_token=None,
        )
        refreshed = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
        self._reprocess_deps._emit(
            job_id=command.job_id,
            asset_id=command.asset_id,
            event_type="manual_result.invalidated",
            message=f"Active result invalidated: {command.reason}",
            metadata={
                "prior_active_result_id": prior_active,
                "actor": command.actor,
                "reason": command.reason,
            },
        )
        logger.info(
            "processing_ui.result_invalidated job_id=%s asset_id=%s",
            command.job_id,
            command.asset_id,
        )
        return {
            "asset_id": command.asset_id,
            "state_version": refreshed.version if refreshed else state.version + 1,
            "status": refreshed.status.value if refreshed else "PENDING_MANUAL_REVIEW",
        }


__all__ = [
    "InvalidateAssetResultCommand",
    "InvalidateAssetResultUseCase",
    "ReprocessAssetCommand",
    "ReprocessAssetUseCase",
]
