"""Phase 7 — available actions, sanitizer, reprocess concurrency / flags."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.application.errors import (
    AssetProcessingStateConcurrencyError,
    ProcessingObservabilityDisabledError,
    StrategyDisabledError,
)
from src.application.services.image_processing.available_asset_actions import (
    compute_available_actions,
)
from src.application.services.image_processing.processing_evidence_sanitizer import (
    sanitize_attempt_view,
    sanitize_metadata,
)
from src.application.use_cases.processing.reprocess_asset import (
    ReprocessAssetCommand,
    ReprocessAssetUseCase,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)


def _now() -> datetime:
    return datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def test_sanitize_metadata_strips_secrets() -> None:
    raw = {
        "api_key": "sk-secret",
        "prompt": "full prompt",
        "provider": "gemini",
        "nested": {"token": "x", "ok": 1},
        "full_text": "ocr dump",
    }
    out = sanitize_metadata(raw)
    assert "api_key" not in out
    assert "prompt" not in out
    assert "full_text" not in out
    assert out["provider"] == "gemini"
    assert "token" not in out["nested"]
    assert out["nested"]["ok"] == 1


def test_sanitize_attempt_view_drops_full_text() -> None:
    view = sanitize_attempt_view(
        {
            "id": "a1",
            "normalized_result": {"internal_code": "X", "full_text": "secret", "quantity": 2},
            "extra": {"worker_token": "t", "provider": "ocr"},
            "worker_token": "t",
        }
    )
    assert view["normalized_result"]["internal_code"] == "X"
    assert "full_text" not in view["normalized_result"]
    assert "worker_token" not in view
    assert "worker_token" not in view["extra"]


def test_available_actions_respect_flags_and_status() -> None:
    job = MagicMock()
    state = JobAssetProcessingState(
        id="s1",
        job_id="j1",
        asset_id="a1",
        status=JobAssetProcessingStatus.PENDING_MANUAL_REVIEW,
        created_at=_now(),
        updated_at=_now(),
        version=3,
        active_result_id=None,
    )
    flags = {
        "processing_observability_enabled": True,
        "processing_asset_reprocess_enabled": True,
        "processing_manual_actions_enabled": True,
        "external_fallback_per_image_enabled": True,
    }
    actions = compute_available_actions(
        job=job,
        state=state,
        has_manual_result=False,
        has_reusable_external_normalized=True,
        flags=flags,
    )
    assert actions.can_reprocess is True
    assert actions.can_send_to_external is True
    assert actions.can_retry_persistence is True
    assert actions.can_assign_manual is True

    processing = JobAssetProcessingState(
        id="s2",
        job_id="j1",
        asset_id="a1",
        status=JobAssetProcessingStatus.PROCESSING,
        created_at=_now(),
        updated_at=_now(),
        version=4,
    )
    busy = compute_available_actions(
        job=job,
        state=processing,
        has_manual_result=False,
        has_reusable_external_normalized=False,
        flags=flags,
    )
    assert busy.can_reprocess is False
    assert busy.can_assign_manual is False


def test_available_actions_disabled_when_observability_off() -> None:
    job = MagicMock()
    state = JobAssetProcessingState(
        id="s1",
        job_id="j1",
        asset_id="a1",
        status=JobAssetProcessingStatus.RESOLVED,
        created_at=_now(),
        updated_at=_now(),
        version=1,
        active_result_id="r1",
    )
    actions = compute_available_actions(
        job=job,
        state=state,
        has_manual_result=True,
        has_reusable_external_normalized=False,
        flags={"processing_observability_enabled": False},
    )
    assert actions.can_reprocess is False
    assert actions.can_invalidate is False


def _build_reprocess_uc(
    *,
    state_repo: MemoryJobAssetProcessingStateRepository,
    monkeypatch: pytest.MonkeyPatch,
    obs: bool = True,
    reprocess: bool = True,
    fallback: bool = True,
) -> ReprocessAssetUseCase:
    inventory_repo = MagicMock()
    inventory_repo.get_by_id.return_value = SimpleNamespace(id="inv1")
    aisle_repo = MagicMock()
    aisle_repo.get_by_id.return_value = SimpleNamespace(id="aisle1", inventory_id="inv1")
    job_repo = MagicMock()
    job_repo.get_by_id.return_value = SimpleNamespace(
        id="job1", target_id="aisle1", status=SimpleNamespace(value="RUNNING")
    )
    job_source = MagicMock()
    job_source.list_by_job.return_value = [
        SimpleNamespace(source_asset_id="asset1"),
    ]
    clock = MagicMock()
    clock.now.return_value = _now()

    monkeypatch.setattr(
        "src.application.use_cases.processing.reprocess_asset.load_settings",
        lambda: SimpleNamespace(
            processing_observability_enabled=obs,
            processing_asset_reprocess_enabled=reprocess,
            external_fallback_per_image_enabled=fallback,
            processing_events_persistence_enabled=False,
        ),
    )
    return ReprocessAssetUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        state_repo=state_repo,
        job_source_asset_repo=job_source,
        clock=clock,
        event_repo=None,
    )


def test_reprocess_queues_pending_and_bumps_version(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MemoryJobAssetProcessingStateRepository()
    state = JobAssetProcessingState(
        id=str(uuid4()),
        job_id="job1",
        asset_id="asset1",
        status=JobAssetProcessingStatus.RESOLVED,
        created_at=_now(),
        updated_at=_now(),
        version=4,
        active_result_id="res1",
        attempt_count=2,
        last_strategy="INTERNAL_OCR",
    )
    repo.save(state)
    uc = _build_reprocess_uc(state_repo=repo, monkeypatch=monkeypatch)
    out = uc.execute(
        ReprocessAssetCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            job_id="job1",
            asset_id="asset1",
            reason="MANUAL_REPROCESS",
            expected_state_version=4,
            strategy="INTERNAL_OCR",
            idempotency_key="k1",
        )
    )
    assert out["status"] == "PENDING"
    assert out["state_version"] == 5
    refreshed = repo.get_by_job_and_asset("job1", "asset1")
    assert refreshed is not None
    assert refreshed.status is JobAssetProcessingStatus.PENDING
    assert refreshed.active_result_id == "res1"
    assert refreshed.attempt_count == 2


def test_reprocess_concurrency_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MemoryJobAssetProcessingStateRepository()
    repo.save(
        JobAssetProcessingState(
            id=str(uuid4()),
            job_id="job1",
            asset_id="asset1",
            status=JobAssetProcessingStatus.RESOLVED,
            created_at=_now(),
            updated_at=_now(),
            version=2,
        )
    )
    uc = _build_reprocess_uc(state_repo=repo, monkeypatch=monkeypatch)
    with pytest.raises(AssetProcessingStateConcurrencyError):
        uc.execute(
            ReprocessAssetCommand(
                inventory_id="inv1",
                aisle_id="aisle1",
                job_id="job1",
                asset_id="asset1",
                reason="MANUAL_REPROCESS",
                expected_state_version=1,
            )
        )


def test_reprocess_idempotent_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MemoryJobAssetProcessingStateRepository()
    repo.save(
        JobAssetProcessingState(
            id=str(uuid4()),
            job_id="job1",
            asset_id="asset1",
            status=JobAssetProcessingStatus.UNRECOGNIZED,
            created_at=_now(),
            updated_at=_now(),
            version=1,
        )
    )
    uc = _build_reprocess_uc(state_repo=repo, monkeypatch=monkeypatch)
    cmd = ReprocessAssetCommand(
        inventory_id="inv1",
        aisle_id="aisle1",
        job_id="job1",
        asset_id="asset1",
        reason="MANUAL_REPROCESS",
        expected_state_version=1,
        idempotency_key="same-key",
    )
    first = uc.execute(cmd)
    second = uc.execute(
        ReprocessAssetCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            job_id="job1",
            asset_id="asset1",
            reason="MANUAL_REPROCESS",
            expected_state_version=first["state_version"],
            idempotency_key="same-key",
        )
    )
    assert second.get("idempotent_replay") is True
    assert repo.get_by_job_and_asset("job1", "asset1").version == first["state_version"]


def test_reprocess_disabled_by_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MemoryJobAssetProcessingStateRepository()
    uc = _build_reprocess_uc(state_repo=repo, monkeypatch=monkeypatch, obs=False)
    with pytest.raises(ProcessingObservabilityDisabledError):
        uc.execute(
            ReprocessAssetCommand(
                inventory_id="inv1",
                aisle_id="aisle1",
                job_id="job1",
                asset_id="asset1",
                reason="x",
                expected_state_version=1,
            )
        )
    uc2 = _build_reprocess_uc(
        state_repo=repo, monkeypatch=monkeypatch, obs=True, reprocess=False
    )
    with pytest.raises(StrategyDisabledError):
        uc2.execute(
            ReprocessAssetCommand(
                inventory_id="inv1",
                aisle_id="aisle1",
                job_id="job1",
                asset_id="asset1",
                reason="x",
                expected_state_version=1,
            )
        )
