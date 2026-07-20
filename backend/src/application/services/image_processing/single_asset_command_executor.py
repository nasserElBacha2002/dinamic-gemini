"""Single-asset command executor — works for active and terminal jobs."""

from __future__ import annotations

import logging
from typing import Any, Callable
from uuid import uuid4

from src.application.ports.asset_processing_command_repository import (
    AssetProcessingCommandRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.external_image_analysis_request_repository import (
    ExternalImageAnalysisRequestRepository,
)
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
)
from src.application.ports.repositories import JobRepository, SourceAssetRepository
from src.application.services.image_processing.external_fallback_recovery import (
    ExternalFallbackRecoveryService,
)
from src.application.services.image_processing.processing_event_publisher import (
    NoOpProcessingEventPublisher,
    ProcessingEventPublisher,
)
from src.domain.image_processing.asset_processing_command import (
    AssetProcessingCommand,
    AssetProcessingCommandStatus,
    AssetProcessingCommandType,
)
from src.domain.image_processing.external_image_analysis_request import (
    ExternalRequestStatus,
)
from src.domain.image_processing.job_asset_processing_state import JobAssetProcessingStatus

logger = logging.getLogger(__name__)


class SingleAssetCommandExecutor:
    """Claim and execute one durable asset_processing_commands row.

    REPROCESS_FROM_SOURCE / SEND_TO_EXTERNAL reset state to PENDING then invoke
    an optional process_asset callback (wired to SingleAssetStrategyProcessor).

    RETRY_PERSISTENCE reuses durable normalized external results — never calls provider.

    RECONCILE_RESULT publishes a reconcile event for recovery without OCR/provider.
    """

    def __init__(
        self,
        *,
        command_repo: AssetProcessingCommandRepository,
        state_repo: JobAssetProcessingStateRepository,
        job_repo: JobRepository,
        source_asset_repo: SourceAssetRepository,
        clock: Clock,
        external_request_repo: ExternalImageAnalysisRequestRepository | None = None,
        event_publisher: ProcessingEventPublisher | None = None,
        process_asset: Callable[..., Any] | None = None,
        persist_reused_result: Callable[..., Any] | None = None,
    ) -> None:
        self._command_repo = command_repo
        self._state_repo = state_repo
        self._job_repo = job_repo
        self._source_asset_repo = source_asset_repo
        self._clock = clock
        self._external_request_repo = external_request_repo
        self._events = event_publisher or NoOpProcessingEventPublisher()
        self._process_asset = process_asset
        self._persist_reused = persist_reused_result
        self._recovery = ExternalFallbackRecoveryService()

    def execute_command(self, command_id: str, *, worker_token: str | None = None) -> dict:
        token = worker_token or f"single-asset-{uuid4()}"
        now = self._clock.now()
        claimed = self._command_repo.try_claim(command_id, worker_token=token, now=now)
        if claimed is None:
            existing = self._command_repo.get_by_id(command_id)
            return {
                "command_id": command_id,
                "status": existing.status.value if existing else "MISSING",
                "claimed": False,
            }
        return self._run_claimed(claimed, worker_token=token)

    def execute_next(self, *, job_id: str | None = None, worker_token: str | None = None) -> dict | None:
        token = worker_token or f"single-asset-{uuid4()}"
        now = self._clock.now()
        claimed = self._command_repo.try_claim_next_queued(
            worker_token=token, now=now, job_id=job_id
        )
        if claimed is None:
            return None
        return self._run_claimed(claimed, worker_token=token)

    def _run_claimed(self, command: AssetProcessingCommand, *, worker_token: str) -> dict:
        now = self._clock.now()
        self._command_repo.mark_running(command, now=now)
        self._events.publish(
            job_id=command.job_id,
            asset_id=command.asset_id,
            event_type="asset.command_claimed",
            strategy=command.requested_strategy,
            message=f"Command claimed: {command.command_type.value}",
            metadata={"command_id": command.id, "worker_token_hash": worker_token[:8]},
        )
        try:
            if command.command_type is AssetProcessingCommandType.RETRY_PERSISTENCE:
                result = self._retry_persistence(command)
            elif command.command_type is AssetProcessingCommandType.RECONCILE_RESULT:
                result = self._reconcile(command)
            else:
                result = self._reprocess_or_external(command, worker_token=worker_token)
            command.status = AssetProcessingCommandStatus.SUCCEEDED
            command.error_code = None
            command.error_message = None
            self._command_repo.mark_finished(command, now=self._clock.now())
            self._events.publish(
                job_id=command.job_id,
                asset_id=command.asset_id,
                event_type="asset.command_succeeded",
                strategy=command.requested_strategy,
                message="Command succeeded",
                metadata={"command_id": command.id, **(result or {})},
            )
            return {
                "command_id": command.id,
                "status": "SUCCEEDED",
                "claimed": True,
                **(result or {}),
            }
        except Exception as exc:
            command.status = AssetProcessingCommandStatus.FAILED
            command.error_code = type(exc).__name__
            command.error_message = str(exc)[:2000]
            self._command_repo.mark_finished(command, now=self._clock.now())
            self._events.publish(
                job_id=command.job_id,
                asset_id=command.asset_id,
                event_type="asset.command_failed",
                severity="ERROR",
                strategy=command.requested_strategy,
                message=str(exc)[:500],
                error_code=command.error_code,
                metadata={"command_id": command.id},
            )
            logger.exception(
                "single_asset_executor.failed command_id=%s type=%s",
                command.id,
                command.command_type.value,
            )
            return {
                "command_id": command.id,
                "status": "FAILED",
                "claimed": True,
                "error_code": command.error_code,
                "error_message": command.error_message,
            }

    def _prepare_pending(
        self, command: AssetProcessingCommand, *, worker_token: str
    ) -> None:
        state = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
        if state is None:
            raise RuntimeError("Missing job asset processing state")
        # Do not overwrite last_strategy with requested — keep historical.
        # Requested strategy lives on the command row.
        expected = state.version
        state.status = JobAssetProcessingStatus.PENDING
        state.error_code = None
        state.error_message = None
        state.worker_token = None
        state.lease_expires_at = None
        state.started_at = None
        state.finished_at = None
        state.updated_at = self._clock.now()
        state.version = expected + 1
        self._state_repo.save_with_ownership(
            state, expected_version=expected, worker_token=None
        )

    def _reprocess_or_external(
        self, command: AssetProcessingCommand, *, worker_token: str
    ) -> dict:
        self._prepare_pending(command, worker_token=worker_token)
        strategy = command.requested_strategy or "AUTO"
        self._events.publish(
            job_id=command.job_id,
            asset_id=command.asset_id,
            event_type="strategy.started",
            strategy=strategy,
            message=f"Single-asset execution started ({command.command_type.value})",
            metadata={"command_id": command.id},
        )
        if self._process_asset is None:
            # Durable queue only — worker will pick PENDING via existing orchestrator
            # or a follow-up poll of this executor with process_asset wired.
            return {"queued_for_processor": True, "requested_strategy": strategy}
        job = self._job_repo.get_by_id(command.job_id)
        asset = self._source_asset_repo.get_by_id(command.asset_id)
        if job is None or asset is None:
            raise RuntimeError("Job or asset missing for single-asset execution")
        self._process_asset(
            job=job,
            asset=asset,
            strategy=strategy,
            command=command,
            worker_token=worker_token,
        )
        return {"executed": True, "requested_strategy": strategy}

    def _retry_persistence(self, command: AssetProcessingCommand) -> dict:
        if self._external_request_repo is None:
            raise RuntimeError("External request repository required for RETRY_PERSISTENCE")
        requests = list(
            self._external_request_repo.list_by_job_and_asset(
                command.job_id, command.asset_id
            )
        )
        reusable = None
        for req in reversed(requests):
            decision = self._recovery.decide(req)
            if decision.action in {"REUSE_NORMALIZED", "RECONCILE_PERSISTED"}:
                reusable = req
                break
        if reusable is None:
            raise RuntimeError("No durable normalized external result to reuse")
        self._events.publish(
            job_id=command.job_id,
            asset_id=command.asset_id,
            event_type="persistence.started",
            strategy="EXTERNAL_PROVIDER",
            message="Retry persistence without provider call",
            metadata={
                "command_id": command.id,
                "request_id": reusable.id,
                "reused_normalized_response": True,
            },
        )
        job = self._job_repo.get_by_id(command.job_id)
        asset = self._source_asset_repo.get_by_id(command.asset_id)
        if job is None or asset is None:
            raise RuntimeError("Job or asset missing")
        result = self._recovery.result_from_stored(
            reusable, job, asset, reason="RETRY_PERSISTENCE"
        )
        if self._persist_reused is not None:
            self._persist_reused(job=job, asset=asset, result=result, request=reusable)
        elif reusable.status is not ExternalRequestStatus.PERSISTED:
            reusable.status = ExternalRequestStatus.PERSISTENCE_PENDING
            reusable.updated_at = self._clock.now()
            self._external_request_repo.save(reusable)
        self._events.publish(
            job_id=command.job_id,
            asset_id=command.asset_id,
            event_type="persistence.completed",
            strategy="EXTERNAL_PROVIDER",
            message="Persistence retry completed (no provider call)",
            metadata={"command_id": command.id, "request_id": reusable.id},
        )
        return {
            "reused_request_id": reusable.id,
            "provider_called": False,
        }

    def _reconcile(self, command: AssetProcessingCommand) -> dict:
        self._events.publish(
            job_id=command.job_id,
            asset_id=command.asset_id,
            event_type="recovery.reconciled",
            message="Reconcile existing result/position",
            metadata={"command_id": command.id},
        )
        return {"reconciled": True}


__all__ = ["SingleAssetCommandExecutor"]
