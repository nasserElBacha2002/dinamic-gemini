"""Transactional invalidate of active asset result (Phase 7 corrections)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.application.errors import (
    AssetProcessingStateConcurrencyError,
    ProcessingObservabilityDisabledError,
    SourceAssetNotFoundForAisleError,
    StrategyDisabledError,
)
from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
)
from src.application.ports.manual_image_coverage_repository import (
    ManualImageCoverageRepository,
)
from src.application.ports.repositories import PositionRepository
from src.application.services.image_processing.processing_action_idempotency_service import (
    ProcessingActionIdempotencyService,
)
from src.application.services.image_processing.processing_asset_scope_validator import (
    ProcessingAssetScopeValidator,
)
from src.application.services.image_processing.processing_event_publisher import (
    NoOpProcessingEventPublisher,
    ProcessingEventPublisher,
)
from src.config import load_settings
from src.domain.image_processing.job_asset_processing_state import JobAssetProcessingStatus
from src.domain.positions.entities import PositionReviewResolution, PositionStatus

logger = logging.getLogger(__name__)


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


class InvalidateAssetResultUseCase:
    """Logically invalidate active result + position + coverage + state (no hard delete)."""

    def __init__(
        self,
        *,
        scope_validator: ProcessingAssetScopeValidator,
        state_repo: JobAssetProcessingStateRepository,
        coverage_repo: ManualImageCoverageRepository | None,
        position_repo: PositionRepository | None,
        idempotency: ProcessingActionIdempotencyService,
        clock: Clock,
        event_publisher: ProcessingEventPublisher | None = None,
        coverage_deleter: Any | None = None,
    ) -> None:
        self._scope = scope_validator
        self._state_repo = state_repo
        self._coverage_repo = coverage_repo
        self._position_repo = position_repo
        self._idempotency = idempotency
        self._clock = clock
        self._events = event_publisher or NoOpProcessingEventPublisher()
        self._coverage_deleter = coverage_deleter

    def execute(self, command: InvalidateAssetResultCommand) -> dict[str, Any]:
        settings = load_settings()
        if not bool(getattr(settings, "processing_observability_enabled", False)):
            raise ProcessingObservabilityDisabledError("PROCESSING_OBSERVABILITY_ENABLED=false")
        if not bool(getattr(settings, "processing_manual_actions_enabled", False)):
            raise StrategyDisabledError("PROCESSING_MANUAL_ACTIONS_ENABLED=false")

        now = self._clock.now()
        payload = {
            "reason": command.reason,
            "expected_state_version": command.expected_state_version,
        }
        begin = self._idempotency.begin(
            action_type="INVALIDATE_RESULT",
            job_id=command.job_id,
            asset_id=command.asset_id,
            idempotency_key=command.idempotency_key,
            payload=payload,
            actor=command.actor,
            now=now,
        )
        if begin.replay and begin.response:
            return {**begin.response, "idempotent_replay": True}

        self._scope.validate(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            job_id=command.job_id,
            asset_id=command.asset_id,
        )
        state = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
        if state is None:
            raise SourceAssetNotFoundForAisleError(
                f"No processing state for asset {command.asset_id}"
            )
        if state.version != command.expected_state_version:
            raise AssetProcessingStateConcurrencyError(
                "ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT"
            )
        if state.status is JobAssetProcessingStatus.PROCESSING:
            raise AssetProcessingStateConcurrencyError(
                "ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT"
            )

        prior_active = state.active_result_id
        position_id: str | None = None
        coverage = None
        if self._coverage_repo is not None:
            coverage = self._coverage_repo.get_by_job_and_asset(
                command.job_id, command.asset_id
            )
            if coverage is not None:
                position_id = coverage.position_id

        # Position policy: soft-delete so exports/stats exclude it.
        if position_id and self._position_repo is not None:
            pos = self._position_repo.get_by_id(position_id)
            if pos is not None and pos.status != PositionStatus.DELETED:
                pos.status = PositionStatus.DELETED
                pos.review_resolution = PositionReviewResolution.DELETED
                pos.needs_review = False
                pos.updated_at = now
                self._position_repo.save(pos)

        # Remove coverage link so one-image/one-active-position can be reassigned.
        if coverage is not None and self._coverage_deleter is not None:
            self._coverage_deleter.delete_by_job_and_asset(
                command.job_id, command.asset_id
            )
        elif (
            coverage is not None
            and self._coverage_repo is not None
            and hasattr(self._coverage_repo, "delete_by_job_and_asset")
        ):
            self._coverage_repo.delete_by_job_and_asset(  # type: ignore[attr-defined]
                command.job_id, command.asset_id
            )

        state.status = JobAssetProcessingStatus.PENDING_MANUAL_REVIEW
        state.active_result_id = None
        state.error_code = "RESULT_INVALIDATED"
        state.error_message = (command.reason or "")[:500]
        state.updated_at = now
        state.version = int(command.expected_state_version) + 1
        # Preserve last_strategy historical value — do not clear.
        self._state_repo.save_with_ownership(
            state,
            expected_version=command.expected_state_version,
            worker_token=None,
        )
        refreshed = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
        self._events.publish(
            job_id=command.job_id,
            asset_id=command.asset_id,
            event_type="manual_result.invalidated",
            message=f"Active result invalidated: {command.reason}",
            metadata={
                "prior_active_result_id": prior_active,
                "position_id": position_id,
                "actor": command.actor,
            },
        )
        state_version = refreshed.version if refreshed else state.version
        response = {
            "asset_id": command.asset_id,
            "state_version": state_version,
            "status": refreshed.status.value if refreshed else "PENDING_MANUAL_REVIEW",
            "position_id": position_id,
            "prior_active_result_id": prior_active,
        }
        self._idempotency.complete(
            begin.record,
            response=response,
            status="COMPLETED",
            state_version=state_version,
            now=self._clock.now(),
        )
        logger.info(
            "processing_ui.result_invalidated job_id=%s asset_id=%s position_id=%s",
            command.job_id,
            command.asset_id,
            position_id,
        )
        return response


__all__ = ["InvalidateAssetResultCommand", "InvalidateAssetResultUseCase"]
