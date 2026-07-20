"""Phase 7 corrections — queue durable asset processing commands (not PENDING alone)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from src.application.errors import (
    AssetProcessingStateConcurrencyError,
    DurableCommandMissingError,
    ProcessingObservabilityDisabledError,
    StrategyDisabledError,
)
from src.application.ports.asset_processing_command_repository import (
    AssetProcessingCommandRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
)
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
from src.domain.image_processing.asset_processing_command import (
    AssetProcessingCommand,
    AssetProcessingCommandStatus,
    AssetProcessingCommandType,
)
from src.domain.image_processing.job_asset_processing_state import JobAssetProcessingStatus

logger = logging.getLogger(__name__)


@dataclass
class QueueAssetCommandInput:
    inventory_id: str
    aisle_id: str
    job_id: str
    asset_id: str
    command_type: AssetProcessingCommandType
    reason: str
    expected_state_version: int
    requested_strategy: str | None = None
    idempotency_key: str | None = None
    actor: str | None = None
    payload: dict[str, Any] | None = None
    action_type: str | None = None


class QueueAssetProcessingCommandUseCase:
    """Persist a durable command; never report QUEUED without a saved row."""

    def __init__(
        self,
        *,
        scope_validator: ProcessingAssetScopeValidator,
        state_repo: JobAssetProcessingStateRepository,
        command_repo: AssetProcessingCommandRepository,
        idempotency: ProcessingActionIdempotencyService,
        clock: Clock,
        event_publisher: ProcessingEventPublisher | None = None,
    ) -> None:
        self._scope = scope_validator
        self._state_repo = state_repo
        self._command_repo = command_repo
        self._idempotency = idempotency
        self._clock = clock
        self._events = event_publisher or NoOpProcessingEventPublisher()

    def execute(self, command: QueueAssetCommandInput) -> dict[str, Any]:
        settings = load_settings()
        if not bool(getattr(settings, "processing_observability_enabled", False)):
            raise ProcessingObservabilityDisabledError("PROCESSING_OBSERVABILITY_ENABLED=false")
        if not bool(getattr(settings, "processing_asset_reprocess_enabled", False)):
            raise StrategyDisabledError("PROCESSING_ASSET_REPROCESS_ENABLED=false")

        action_type = command.action_type or command.command_type.value
        now = self._clock.now()
        payload = {
            "command_type": command.command_type.value,
            "requested_strategy": command.requested_strategy,
            "reason": command.reason,
            "expected_state_version": command.expected_state_version,
            **(command.payload or {}),
        }
        begin = self._idempotency.begin(
            action_type=action_type,
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
            raise AssetProcessingStateConcurrencyError(
                "ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT"
            )
        if state.version != command.expected_state_version:
            raise AssetProcessingStateConcurrencyError(
                "ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT"
            )
        if state.status is JobAssetProcessingStatus.PROCESSING:
            raise AssetProcessingStateConcurrencyError(
                "ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT"
            )
        open_cmds = [
            c
            for c in self._command_repo.list_by_job_asset(command.job_id, command.asset_id)
            if c.status
            in (
                AssetProcessingCommandStatus.QUEUED,
                AssetProcessingCommandStatus.CLAIMED,
                AssetProcessingCommandStatus.RUNNING,
            )
        ]
        if open_cmds:
            raise AssetProcessingStateConcurrencyError(
                "ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT"
            )

        if (
            command.command_type is AssetProcessingCommandType.SEND_TO_EXTERNAL
            and not bool(getattr(settings, "external_fallback_per_image_enabled", False))
        ):
            raise StrategyDisabledError("EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=false")

        cmd = AssetProcessingCommand(
            id=str(uuid4()),
            job_id=command.job_id,
            asset_id=command.asset_id,
            command_type=command.command_type,
            status=AssetProcessingCommandStatus.QUEUED,
            created_at=now,
            requested_strategy=command.requested_strategy,
            idempotency_key=command.idempotency_key,
            expected_state_version=command.expected_state_version,
            actor=command.actor,
            reason=command.reason,
            payload=payload,
        )
        try:
            self._command_repo.save(cmd)
        except (OSError, ValueError, TypeError) as exc:
            raise DurableCommandMissingError(
                f"Failed to persist asset processing command: {exc}"
            ) from exc

        saved = self._command_repo.get_by_id(cmd.id)
        if saved is None or saved.status is not AssetProcessingCommandStatus.QUEUED:
            raise DurableCommandMissingError("Command not durable after save")

        self._events.publish(
            job_id=command.job_id,
            asset_id=command.asset_id,
            event_type="asset.command_queued",
            strategy=command.requested_strategy,
            message=f"Command queued: {command.command_type.value}",
            metadata={
                "command_id": cmd.id,
                "command_type": command.command_type.value,
                "reason": command.reason,
                "actor": command.actor,
            },
        )
        response = {
            "asset_id": command.asset_id,
            "command_id": cmd.id,
            "command_type": command.command_type.value,
            "status": AssetProcessingCommandStatus.QUEUED.value,
            "state_version": state.version,
            "requested_strategy": command.requested_strategy,
        }
        self._idempotency.complete(
            begin.record,
            response=response,
            status="COMPLETED",
            state_version=state.version,
            now=self._clock.now(),
        )
        logger.info(
            "processing_ui.command_queued job_id=%s asset_id=%s type=%s command_id=%s",
            command.job_id,
            command.asset_id,
            command.command_type.value,
            cmd.id,
        )
        return response


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


class ReprocessAssetUseCase:
    def __init__(self, queue_uc: QueueAssetProcessingCommandUseCase) -> None:
        self._queue = queue_uc

    def execute(self, command: ReprocessAssetCommand) -> dict[str, Any]:
        strategy = (command.strategy or "AUTO").strip().upper()
        return self._queue.execute(
            QueueAssetCommandInput(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                job_id=command.job_id,
                asset_id=command.asset_id,
                command_type=AssetProcessingCommandType.REPROCESS_FROM_SOURCE,
                reason=command.reason,
                expected_state_version=command.expected_state_version,
                requested_strategy=None if strategy == "AUTO" else strategy,
                idempotency_key=command.idempotency_key,
                actor=command.actor,
                payload={"manual_policy": command.manual_policy},
                action_type="REPROCESS_FROM_SOURCE",
            )
        )


@dataclass
class RetryPersistenceCommand:
    inventory_id: str
    aisle_id: str
    job_id: str
    asset_id: str
    reason: str
    expected_state_version: int
    idempotency_key: str | None = None
    actor: str | None = None


class RetryAssetPersistenceUseCase:
    def __init__(self, queue_uc: QueueAssetProcessingCommandUseCase) -> None:
        self._queue = queue_uc

    def execute(self, command: RetryPersistenceCommand) -> dict[str, Any]:
        return self._queue.execute(
            QueueAssetCommandInput(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                job_id=command.job_id,
                asset_id=command.asset_id,
                command_type=AssetProcessingCommandType.RETRY_PERSISTENCE,
                reason=command.reason or "RETRY_PERSISTENCE",
                expected_state_version=command.expected_state_version,
                requested_strategy="EXTERNAL_PROVIDER",
                idempotency_key=command.idempotency_key,
                actor=command.actor,
                action_type="RETRY_PERSISTENCE",
            )
        )


@dataclass
class SendToExternalCommand:
    inventory_id: str
    aisle_id: str
    job_id: str
    asset_id: str
    reason: str
    expected_state_version: int
    idempotency_key: str | None = None
    actor: str | None = None


class SendAssetToExternalUseCase:
    def __init__(self, queue_uc: QueueAssetProcessingCommandUseCase) -> None:
        self._queue = queue_uc

    def execute(self, command: SendToExternalCommand) -> dict[str, Any]:
        return self._queue.execute(
            QueueAssetCommandInput(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                job_id=command.job_id,
                asset_id=command.asset_id,
                command_type=AssetProcessingCommandType.SEND_TO_EXTERNAL,
                reason=command.reason or "MANUAL_EXTERNAL_FALLBACK",
                expected_state_version=command.expected_state_version,
                requested_strategy="EXTERNAL_PROVIDER",
                idempotency_key=command.idempotency_key,
                actor=command.actor,
                action_type="SEND_TO_EXTERNAL",
            )
        )


__all__ = [
    "QueueAssetCommandInput",
    "QueueAssetProcessingCommandUseCase",
    "ReprocessAssetCommand",
    "ReprocessAssetUseCase",
    "RetryAssetPersistenceUseCase",
    "RetryPersistenceCommand",
    "SendAssetToExternalUseCase",
    "SendToExternalCommand",
]
