"""Phase 7 corrections — durable commands, idempotency, sanitizer, actions, executor."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.application.errors import (
    AssetProcessingStateConcurrencyError,
    IdempotencyKeyReusedError,
    ProcessingObservabilityDisabledError,
)
from src.application.ports.manual_image_coverage_repository import ManualImageCoverageLink
from src.application.services.image_processing.available_asset_actions import (
    compute_available_actions,
)
from src.application.services.image_processing.processing_action_idempotency_service import (
    ProcessingActionIdempotencyService,
)
from src.application.services.image_processing.processing_asset_scope_validator import (
    ProcessingAssetScopeValidator,
)
from src.application.services.image_processing.processing_event_publisher import (
    RepositoryProcessingEventPublisher,
)
from src.application.services.image_processing.processing_evidence_sanitizer import (
    csv_safe_cell,
    sanitize_metadata,
)
from src.application.services.image_processing.single_asset_command_executor import (
    SingleAssetCommandExecutor,
)
from src.application.use_cases.processing.invalidate_asset_result import (
    InvalidateAssetResultCommand,
    InvalidateAssetResultUseCase,
)
from src.application.use_cases.processing.reprocess_asset import (
    QueueAssetCommandInput,
    QueueAssetProcessingCommandUseCase,
    ReprocessAssetCommand,
    ReprocessAssetUseCase,
    RetryAssetPersistenceUseCase,
    RetryPersistenceCommand,
)
from src.domain.image_processing.asset_processing_command import (
    AssetProcessingCommandType,
)
from src.domain.image_processing.external_image_analysis_request import (
    ExternalImageAnalysisRequest,
    ExternalRequestStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.persistence.memory_manual_image_coverage_repository import (
    MemoryManualImageCoverageRepository,
)
from src.infrastructure.repositories.memory_asset_processing_command_repository import (
    MemoryAssetProcessingCommandRepository,
)
from src.infrastructure.repositories.memory_external_image_analysis_request_repository import (
    MemoryExternalImageAnalysisRequestRepository,
)
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)
from src.infrastructure.repositories.memory_processing_action_idempotency_repository import (
    MemoryProcessingActionIdempotencyRepository,
)
from src.infrastructure.repositories.memory_processing_event_repository import (
    MemoryProcessingEventRepository,
)


def _now() -> datetime:
    return datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def monkeypatch_flags(monkeypatch: pytest.MonkeyPatch):
    def _apply(**kwargs):
        defaults = dict(
            processing_observability_enabled=True,
            processing_asset_reprocess_enabled=True,
            processing_manual_actions_enabled=True,
            processing_events_persistence_enabled=True,
            external_fallback_per_image_enabled=True,
        )
        defaults.update(kwargs)
        monkeypatch.setattr(
            "src.application.use_cases.processing.reprocess_asset.load_settings",
            lambda: SimpleNamespace(**defaults),
        )
        monkeypatch.setattr(
            "src.application.use_cases.processing.invalidate_asset_result.load_settings",
            lambda: SimpleNamespace(**defaults),
        )
        monkeypatch.setattr(
            "src.application.services.image_processing.processing_event_publisher.load_settings",
            lambda: SimpleNamespace(**defaults),
        )

    return _apply


def _scope_and_state():
    inventory_repo = MagicMock()
    inventory_repo.get_by_id.return_value = SimpleNamespace(id="inv1")
    aisle_repo = MagicMock()
    aisle_repo.get_by_id.return_value = SimpleNamespace(id="aisle1", inventory_id="inv1")
    job_repo = MagicMock()
    job_repo.get_by_id.return_value = SimpleNamespace(
        id="job1",
        target_id="aisle1",
        status=SimpleNamespace(value="SUCCEEDED"),
        engine_params_json={
            "identification_execution": {
                "external_fallback": {"enabled": True},
            }
        },
    )
    job_source = MagicMock()
    job_source.list_by_job.return_value = [SimpleNamespace(source_asset_id="asset1")]
    state_repo = MemoryJobAssetProcessingStateRepository()
    state_repo.save(
        JobAssetProcessingState(
            id=str(uuid4()),
            job_id="job1",
            asset_id="asset1",
            status=JobAssetProcessingStatus.RESOLVED,
            created_at=_now(),
            updated_at=_now(),
            version=2,
            active_result_id="res1",
            last_strategy="INTERNAL_OCR",
            attempt_count=1,
        )
    )
    scope = ProcessingAssetScopeValidator(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_source_asset_repo=job_source,
    )
    return scope, state_repo, job_repo


def test_sanitize_public_hides_hashes_and_secrets() -> None:
    out = sanitize_metadata(
        {
            "provider": "gemini",
            "api_key": "secret",
            "request_image_sha256": "abc",
            "prompt": "nope",
        },
        level="PUBLIC_OPERATIONAL",
    )
    assert out == {"provider": "gemini"}
    tech = sanitize_metadata(
        {"provider": "gemini", "request_image_sha256": "abc"},
        level="TECHNICAL_SAFE",
    )
    assert tech["request_image_sha256"] == "abc"


def test_csv_safe_cell_guards_formulas() -> None:
    assert csv_safe_cell("=CMD()") == "'=CMD()"
    assert csv_safe_cell("ok") == "ok"


def test_available_actions_use_job_and_manual_flag() -> None:
    job = SimpleNamespace(
        status=SimpleNamespace(value="SUCCEEDED"),
        engine_params_json={
            "identification_execution": {"external_fallback": {"enabled": True}}
        },
    )
    state = JobAssetProcessingState(
        id="s",
        job_id="j",
        asset_id="a",
        status=JobAssetProcessingStatus.PENDING_MANUAL_REVIEW,
        created_at=_now(),
        updated_at=_now(),
        version=1,
    )
    actions = compute_available_actions(
        job=job,
        state=state,
        has_manual_result=False,
        has_reusable_external_normalized=True,
        flags={
            "processing_observability_enabled": True,
            "processing_asset_reprocess_enabled": True,
            "processing_manual_actions_enabled": False,
            "external_fallback_per_image_enabled": True,
        },
    )
    assert actions.can_assign_manual is False
    assert actions.can_invalidate is False
    assert actions.can_reprocess is True


def test_queue_command_durable_and_idempotent(monkeypatch_flags) -> None:
    monkeypatch_flags()
    scope, state_repo, _job_repo = _scope_and_state()
    cmd_repo = MemoryAssetProcessingCommandRepository()
    idem = ProcessingActionIdempotencyService(MemoryProcessingActionIdempotencyRepository())
    clock = MagicMock()
    clock.now.return_value = _now()
    queue = QueueAssetProcessingCommandUseCase(
        scope_validator=scope,
        state_repo=state_repo,
        command_repo=cmd_repo,
        idempotency=idem,
        clock=clock,
    )
    uc = ReprocessAssetUseCase(queue)
    first = uc.execute(
        ReprocessAssetCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            job_id="job1",
            asset_id="asset1",
            reason="MANUAL_REPROCESS",
            expected_state_version=2,
            strategy="INTERNAL_OCR",
            idempotency_key="k1",
        )
    )
    assert first["status"] == "QUEUED"
    assert first["command_id"]
    assert cmd_repo.get_by_id(first["command_id"]) is not None
    # last_strategy preserved on state
    assert state_repo.get_by_job_and_asset("job1", "asset1").last_strategy == "INTERNAL_OCR"
    second = uc.execute(
        ReprocessAssetCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            job_id="job1",
            asset_id="asset1",
            reason="MANUAL_REPROCESS",
            expected_state_version=2,
            strategy="INTERNAL_OCR",
            idempotency_key="k1",
        )
    )
    assert second.get("idempotent_replay") is True
    assert second["command_id"] == first["command_id"]


def test_idempotency_key_reused_different_payload(monkeypatch_flags) -> None:
    monkeypatch_flags()
    scope, state_repo, _ = _scope_and_state()
    queue = QueueAssetProcessingCommandUseCase(
        scope_validator=scope,
        state_repo=state_repo,
        command_repo=MemoryAssetProcessingCommandRepository(),
        idempotency=ProcessingActionIdempotencyService(
            MemoryProcessingActionIdempotencyRepository()
        ),
        clock=MagicMock(now=lambda: _now()),
    )
    queue.execute(
        QueueAssetCommandInput(
            inventory_id="inv1",
            aisle_id="aisle1",
            job_id="job1",
            asset_id="asset1",
            command_type=AssetProcessingCommandType.REPROCESS_FROM_SOURCE,
            reason="a",
            expected_state_version=2,
            requested_strategy="INTERNAL_OCR",
            idempotency_key="same",
        )
    )
    with pytest.raises(IdempotencyKeyReusedError):
        queue.execute(
            QueueAssetCommandInput(
                inventory_id="inv1",
                aisle_id="aisle1",
                job_id="job1",
                asset_id="asset1",
                command_type=AssetProcessingCommandType.REPROCESS_FROM_SOURCE,
                reason="b",
                expected_state_version=2,
                requested_strategy="CODE_SCAN",
                idempotency_key="same",
            )
        )


def test_retry_persistence_executor_no_provider(monkeypatch_flags) -> None:
    monkeypatch_flags()
    scope, state_repo, job_repo = _scope_and_state()
    state = state_repo.get_by_job_and_asset("job1", "asset1")
    assert state is not None
    state.status = JobAssetProcessingStatus.FAILED_TECHNICAL
    state_repo.save(state)

    cmd_repo = MemoryAssetProcessingCommandRepository()
    ext = MemoryExternalImageAnalysisRequestRepository()
    now = _now()
    ext.save(
        ExternalImageAnalysisRequest(
            id=str(uuid4()),
            idempotency_key="e1",
            job_id="job1",
            asset_id="asset1",
            provider="gemini",
            model="m",
            status=ExternalRequestStatus.PROVIDER_SUCCEEDED,
            normalized_result={"internal_code": "X", "quantity": 2},
            created_at=now,
            updated_at=now,
        )
    )
    clock = MagicMock()
    clock.now.return_value = now
    queue = QueueAssetProcessingCommandUseCase(
        scope_validator=scope,
        state_repo=state_repo,
        command_repo=cmd_repo,
        idempotency=ProcessingActionIdempotencyService(
            MemoryProcessingActionIdempotencyRepository()
        ),
        clock=clock,
    )
    out = RetryAssetPersistenceUseCase(queue).execute(
        RetryPersistenceCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            job_id="job1",
            asset_id="asset1",
            reason="RETRY_PERSISTENCE",
            expected_state_version=state.version,
            idempotency_key="rp1",
        )
    )
    source_repo = MagicMock()
    source_repo.get_by_id.return_value = SimpleNamespace(id="asset1")
    executor = SingleAssetCommandExecutor(
        command_repo=cmd_repo,
        state_repo=state_repo,
        job_repo=job_repo,
        source_asset_repo=source_repo,
        clock=clock,
        external_request_repo=ext,
    )
    result = executor.execute_command(out["command_id"])
    assert result["status"] == "SUCCEEDED"
    assert result["provider_called"] is False


def test_invalidate_marks_position_deleted(monkeypatch_flags) -> None:
    monkeypatch_flags()
    scope, state_repo, _ = _scope_and_state()
    coverage = MemoryManualImageCoverageRepository()
    coverage.save(
        ManualImageCoverageLink(
            id="cov1",
            job_id="job1",
            job_source_asset_id="jsa1",
            source_asset_id="asset1",
            position_id="pos1",
            aisle_id="aisle1",
            inventory_id="inv1",
            created_by_user_id=None,
            created_at=_now(),
        )
    )
    position_repo = MagicMock()
    position_repo.get_by_id.return_value = Position(
        id="pos1",
        aisle_id="aisle1",
        status=PositionStatus.DETECTED,
        confidence=1.0,
        needs_review=True,
        primary_evidence_id=None,
        created_at=_now(),
        updated_at=_now(),
        job_id="job1",
    )
    uc = InvalidateAssetResultUseCase(
        scope_validator=scope,
        state_repo=state_repo,
        coverage_repo=coverage,
        position_repo=position_repo,
        idempotency=ProcessingActionIdempotencyService(
            MemoryProcessingActionIdempotencyRepository()
        ),
        clock=MagicMock(now=lambda: _now()),
    )
    out = uc.execute(
        InvalidateAssetResultCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            job_id="job1",
            asset_id="asset1",
            reason="wrong",
            expected_state_version=2,
            idempotency_key="inv1",
        )
    )
    assert out["status"] == "PENDING_MANUAL_REVIEW"
    assert coverage.get_by_job_and_asset("job1", "asset1") is None
    saved_pos = position_repo.save.call_args[0][0]
    assert saved_pos.status == PositionStatus.DELETED


def test_event_publisher_persists(monkeypatch_flags) -> None:
    monkeypatch_flags()
    events = MemoryProcessingEventRepository()
    pub = RepositoryProcessingEventPublisher(
        event_repo=events, clock=MagicMock(now=lambda: _now())
    )
    pub.publish(
        job_id="job1",
        asset_id="asset1",
        event_type="strategy.started",
        message="start",
        metadata={"api_key": "x", "provider": "ocr"},
    )
    rows = events.list_by_job_asset("job1", "asset1")
    assert len(rows) == 1
    assert rows[0].metadata.get("provider") == "ocr"
    assert "api_key" not in rows[0].metadata


def test_observability_disabled_blocks_queue(monkeypatch_flags) -> None:
    monkeypatch_flags(processing_observability_enabled=False)
    scope, state_repo, _ = _scope_and_state()
    queue = QueueAssetProcessingCommandUseCase(
        scope_validator=scope,
        state_repo=state_repo,
        command_repo=MemoryAssetProcessingCommandRepository(),
        idempotency=ProcessingActionIdempotencyService(
            MemoryProcessingActionIdempotencyRepository()
        ),
        clock=MagicMock(now=lambda: _now()),
    )
    with pytest.raises(ProcessingObservabilityDisabledError):
        queue.execute(
            QueueAssetCommandInput(
                inventory_id="inv1",
                aisle_id="aisle1",
                job_id="job1",
                asset_id="asset1",
                command_type=AssetProcessingCommandType.REPROCESS_FROM_SOURCE,
                reason="x",
                expected_state_version=2,
            )
        )


def test_concurrent_open_command_conflicts(monkeypatch_flags) -> None:
    monkeypatch_flags()
    scope, state_repo, _ = _scope_and_state()
    cmd_repo = MemoryAssetProcessingCommandRepository()
    queue = QueueAssetProcessingCommandUseCase(
        scope_validator=scope,
        state_repo=state_repo,
        command_repo=cmd_repo,
        idempotency=ProcessingActionIdempotencyService(
            MemoryProcessingActionIdempotencyRepository()
        ),
        clock=MagicMock(now=lambda: _now()),
    )
    queue.execute(
        QueueAssetCommandInput(
            inventory_id="inv1",
            aisle_id="aisle1",
            job_id="job1",
            asset_id="asset1",
            command_type=AssetProcessingCommandType.REPROCESS_FROM_SOURCE,
            reason="first",
            expected_state_version=2,
            idempotency_key="a",
        )
    )
    with pytest.raises(AssetProcessingStateConcurrencyError):
        queue.execute(
            QueueAssetCommandInput(
                inventory_id="inv1",
                aisle_id="aisle1",
                job_id="job1",
                asset_id="asset1",
                command_type=AssetProcessingCommandType.REPROCESS_FROM_SOURCE,
                reason="second",
                expected_state_version=2,
                idempotency_key="b",
            )
        )
