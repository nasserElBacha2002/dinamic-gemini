"""Dispatch tests: AUTO / CODE_SCAN_ONLY / VISION_ONLY on CodeScanAssetProcessor."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.services.image_processing.code_scan_asset_processor import (
    CodeScanAssetProcessor,
)
from src.application.services.image_processing.external_provider_fallback_orchestrator import (
    ExternalFallbackOutcome,
)
from src.application.services.image_processing.processing_result_persister import (
    PersistOutcome,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import (
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.aisle_identification.processing_mode import VISION_ONLY_DIRECT_ERROR_CODE
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.jobs.entities import Job, JobStatus


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 3, 1, tzinfo=timezone.utc)


class _Strategy:
    strategy_key = "CODE_SCAN"
    attempt_provider = "code_scan"
    attempt_model = "local"

    def __init__(self) -> None:
        self.calls = 0

    def process(self, context, asset) -> ImageProcessingResult:
        self.calls += 1
        return ImageProcessingResult(
            job_id=context.job_id,
            asset_id=context.asset_id,
            status=ImageResultStatus.UNRECOGNIZED,
            processing_mode="CODE_SCAN",
            resolved_by="CODE_SCAN",
            error_code="MISSING_INTERNAL_CODE",
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )


class _Fallback:
    counters = None

    def __init__(self) -> None:
        self.calls = 0
        self.last_internal: ImageProcessingResult | None = None

    def process_if_eligible(self, **kwargs):
        self.calls += 1
        internal = kwargs["internal_result"]
        self.last_internal = internal
        return ExternalFallbackOutcome(
            skipped=False,
            cancelled=False,
            result=ImageProcessingResult(
                job_id=internal.job_id,
                asset_id=internal.asset_id,
                status=ImageResultStatus.RESOLVED_EXTERNAL,
                processing_mode="EXTERNAL_PROVIDER",
                resolved_by="EXTERNAL_PROVIDER",
                internal_code="SKU1",
                quantity=1.0,
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            ),
            attempt=None,
            request=None,
        )

    def finalize_after_persist(self, **kwargs) -> None:
        return None


def _job(*, processing_mode: str, fallback_enabled: bool) -> Job:
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    return Job(
        id="job-pm",
        job_type="process_aisle",
        target_type="aisle",
        target_id="aisle-1",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        identification_mode_source=AisleIdentificationModeSource.REQUEST,
        configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        engine_params_json={
            "identification_execution": {
                "processing_mode": processing_mode,
                "executed_strategy": "CODE_SCAN",
                "external_fallback": {
                    "fallback_enabled": fallback_enabled,
                    "fallback_provider": "gemini",
                    "fallback_model": "m1",
                    "fallback_mode": "PER_ASSET",
                },
            }
        },
    )


def _build():
    strategy = _Strategy()
    fallback = _Fallback()
    clock = _Clock()
    now = clock.now()
    state = JobAssetProcessingState(
        id="st1",
        job_id="job-pm",
        asset_id="asset-1",
        status=JobAssetProcessingStatus.PENDING,
        attempt_count=0,
        created_at=now,
        updated_at=now,
    )
    state_repo = MagicMock()
    state_repo.get_by_job_and_asset.return_value = state
    orch = MagicMock()
    orch.is_terminal.return_value = False
    orch.acquire_for_processing.return_value = state
    persister = MagicMock()
    persister.persist.return_value = PersistOutcome(
        persisted=True, position_id="pos-1", active_result_id="ar-1"
    )
    attempt_repo = MagicMock()
    proc = CodeScanAssetProcessor(
        strategy=strategy,
        image_orchestrator=orch,
        result_persister=persister,
        attempt_repo=attempt_repo,
        state_repo=state_repo,
        clock=clock,
        attempts_enabled=False,
        external_fallback=fallback,
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    asset = SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="a.jpg",
        storage_path="/a.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )
    return proc, strategy, fallback, aisle, asset


def test_vision_only_skips_code_scan_and_calls_vision():
    proc, strategy, fallback, aisle, asset = _build()
    job = _job(processing_mode="VISION_ONLY", fallback_enabled=True)
    out = proc.process_asset(
        job=job, aisle=aisle, asset=asset, strategy_key="CODE_SCAN", worker_token="w1"
    )
    assert out.processed is True
    assert strategy.calls == 0
    assert fallback.calls == 1
    assert fallback.last_internal is not None
    assert fallback.last_internal.error_code == VISION_ONLY_DIRECT_ERROR_CODE
    assert fallback.last_internal.evidence.get("code_scan_invoked") is False


def test_code_scan_only_never_calls_vision_even_on_miss():
    proc, strategy, fallback, aisle, asset = _build()
    job = _job(processing_mode="CODE_SCAN_ONLY", fallback_enabled=False)
    out = proc.process_asset(
        job=job, aisle=aisle, asset=asset, strategy_key="CODE_SCAN", worker_token="w1"
    )
    assert out.processed is True
    assert strategy.calls == 1
    assert fallback.calls == 0


def test_auto_calls_vision_after_code_scan_miss():
    proc, strategy, fallback, aisle, asset = _build()
    job = _job(processing_mode="AUTO", fallback_enabled=True)
    out = proc.process_asset(
        job=job, aisle=aisle, asset=asset, strategy_key="CODE_SCAN", worker_token="w1"
    )
    assert out.processed is True
    assert strategy.calls == 1
    assert fallback.calls == 1
