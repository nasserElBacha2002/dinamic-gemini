"""Image-level orchestrator — acquire, attempt, strategy, persist state (Phase 2)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
    ProcessingAttemptRepository,
)
from src.domain.image_processing.contracts import (
    ImageProcessingContext,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)

logger = logging.getLogger(__name__)

_TERMINAL = frozenset(
    {
        JobAssetProcessingStatus.RESOLVED,
        JobAssetProcessingStatus.UNRECOGNIZED,
        JobAssetProcessingStatus.FAILED_TECHNICAL,
        JobAssetProcessingStatus.PENDING_MANUAL_REVIEW,
        JobAssetProcessingStatus.CANCELLED,
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImageProcessingOrchestrator:
    def __init__(
        self,
        state_repo: JobAssetProcessingStateRepository,
        attempt_repo: ProcessingAttemptRepository,
        clock: Clock,
        *,
        attempts_enabled: bool = True,
    ) -> None:
        self._state_repo = state_repo
        self._attempt_repo = attempt_repo
        self._clock = clock
        self._attempts_enabled = attempts_enabled

    def is_terminal(self, state: JobAssetProcessingState | None) -> bool:
        return state is not None and state.status in _TERMINAL

    def acquire_for_processing(
        self,
        *,
        job_id: str,
        asset_id: str,
        strategy: str,
        worker_token: str | None = None,
    ) -> JobAssetProcessingState | None:
        state = self._state_repo.get_by_job_and_asset(job_id, asset_id)
        if self.is_terminal(state):
            logger.info(
                "image_orchestrator.skip_already_terminal job_id=%s asset_id=%s status=%s",
                job_id,
                asset_id,
                state.status.value if state else None,
            )
            return None
        # FAILED_TECHNICAL is terminal within the same job (Phase 2 policy) — never re-acquired
        # here; only PENDING assets are eligible for (re-)acquisition.
        acquired = self._state_repo.try_acquire(
            job_id,
            asset_id,
            expected_statuses=(JobAssetProcessingStatus.PENDING,),
            next_status=JobAssetProcessingStatus.PROCESSING,
            strategy=strategy,
            now=self._clock.now(),
            worker_token=worker_token,
        )
        if acquired is None:
            logger.info(
                "image_orchestrator.acquire_lost_race job_id=%s asset_id=%s",
                job_id,
                asset_id,
            )
        return acquired

    def start_attempt(
        self,
        context: ImageProcessingContext,
        *,
        strategy: str,
    ) -> ProcessingAttempt | None:
        if not self._attempts_enabled:
            return None
        now = self._clock.now()
        number = self._attempt_repo.next_attempt_number(
            context.job_id, context.asset_id, strategy
        )
        existing = self._attempt_repo.get_by_unique_key(
            context.job_id, context.asset_id, strategy, number
        )
        if existing is not None:
            return existing
        attempt = ProcessingAttempt(
            id=str(uuid.uuid4()),
            job_id=context.job_id,
            asset_id=context.asset_id,
            strategy=strategy,
            attempt_number=number,
            status=ProcessingAttemptStatus.STARTED,
            created_at=now,
            provider=context.provider_name,
            model=context.model_name,
            started_at=now,
            execution_scope=context.execution_scope.value,
            logical_asset_attempt=True,
            configuration_snapshot_version=context.configuration_snapshot_version,
        )
        self._attempt_repo.save(attempt)
        logger.info(
            "image_orchestrator.attempt_started job_id=%s asset_id=%s attempt_id=%s "
            "attempt_number=%s strategy=%s execution_scope=%s",
            context.job_id,
            context.asset_id,
            attempt.id,
            attempt.attempt_number,
            strategy,
            context.execution_scope.value,
        )
        return attempt

    def finalize_from_result(
        self,
        *,
        state: JobAssetProcessingState,
        attempt: ProcessingAttempt | None,
        result: ImageProcessingResult,
        strategy: str,
    ) -> JobAssetProcessingState:
        now = self._clock.now()
        expected_version = int(state.version or 1)
        owner_token = state.worker_token
        status = self._map_result_status(result.status)
        started = state.started_at or now
        duration = int((now - started).total_seconds() * 1000)
        state.status = status
        state.last_strategy = strategy
        state.finished_at = now
        state.duration_ms = duration
        # Attempt bookkeeping (attempt rows) is gated by attempts_enabled, but the state's own
        # attempt_count must always reflect one processing pass regardless of that flag.
        state.attempt_count = int(state.attempt_count or 0) + 1
        state.error_code = result.error_code
        state.error_message = result.error_message
        state.execution_scope = result.execution_scope.value
        active_result_id = (result.additional_fields or {}).get("active_result_id")
        if active_result_id:
            state.active_result_id = active_result_id
        state.updated_at = now
        state.version = expected_version + 1
        self._state_repo.save_with_ownership(
            state, expected_version=expected_version, worker_token=owner_token
        )

        if attempt is not None and self._attempts_enabled:
            self.complete_attempt_from_result(attempt=attempt, result=result, duration_ms=duration)

        logger.info(
            "image_orchestrator.asset_finalized job_id=%s asset_id=%s status=%s "
            "strategy=%s duration_ms=%s",
            state.job_id,
            state.asset_id,
            state.status.value,
            strategy,
            duration,
        )
        return state

    def complete_attempt_from_result(
        self,
        *,
        attempt: ProcessingAttempt,
        result: ImageProcessingResult,
        duration_ms: int | None = None,
    ) -> None:
        """Close one attempt without finalizing asset state (Phase 5 internal→external handoff)."""
        if not self._attempts_enabled:
            return
        now = self._clock.now()
        attempt.status = self._map_attempt_status(result.status)
        attempt.finished_at = now
        if duration_ms is not None:
            attempt.duration_ms = duration_ms
        elif attempt.started_at is not None:
            attempt.duration_ms = int((now - attempt.started_at).total_seconds() * 1000)
        elif result.processing_duration_ms is not None:
            attempt.duration_ms = result.processing_duration_ms
        attempt.error_code = result.error_code
        attempt.error_message = result.error_message
        attempt.normalized_result = result.normalized_result
        attempt.validation_result = {
            "errors": list(result.validation_errors),
            "warnings": list(result.warnings),
        }
        attempt.execution_scope = result.execution_scope.value
        self._attempt_repo.save(attempt)

    def mark_cancelled(self, state: JobAssetProcessingState, attempt: ProcessingAttempt | None) -> None:
        now = self._clock.now()
        expected_version = int(state.version or 1)
        owner_token = state.worker_token
        state.status = JobAssetProcessingStatus.CANCELLED
        state.finished_at = now
        state.updated_at = now
        state.version = expected_version + 1
        self._state_repo.save_with_ownership(
            state, expected_version=expected_version, worker_token=owner_token
        )
        if attempt is not None and self._attempts_enabled:
            attempt.status = ProcessingAttemptStatus.CANCELLED
            attempt.finished_at = now
            self._attempt_repo.save(attempt)

    @staticmethod
    def _map_result_status(status: ImageResultStatus) -> JobAssetProcessingStatus:
        mapping = {
            ImageResultStatus.RESOLVED_INTERNAL: JobAssetProcessingStatus.RESOLVED,
            ImageResultStatus.RESOLVED_EXTERNAL: JobAssetProcessingStatus.RESOLVED,
            ImageResultStatus.UNRECOGNIZED: JobAssetProcessingStatus.UNRECOGNIZED,
            ImageResultStatus.FAILED_TECHNICAL: JobAssetProcessingStatus.FAILED_TECHNICAL,
            ImageResultStatus.PENDING_MANUAL_REVIEW: JobAssetProcessingStatus.PENDING_MANUAL_REVIEW,
        }
        return mapping.get(status, JobAssetProcessingStatus.FAILED_TECHNICAL)

    @staticmethod
    def _map_attempt_status(status: ImageResultStatus) -> ProcessingAttemptStatus:
        mapping = {
            ImageResultStatus.RESOLVED_INTERNAL: ProcessingAttemptStatus.SUCCEEDED,
            ImageResultStatus.RESOLVED_EXTERNAL: ProcessingAttemptStatus.SUCCEEDED,
            ImageResultStatus.UNRECOGNIZED: ProcessingAttemptStatus.UNRECOGNIZED,
            ImageResultStatus.FAILED_TECHNICAL: ProcessingAttemptStatus.FAILED_TECHNICAL,
            ImageResultStatus.PENDING_MANUAL_REVIEW: ProcessingAttemptStatus.INVALID,
        }
        return mapping.get(status, ProcessingAttemptStatus.FAILED_TECHNICAL)
