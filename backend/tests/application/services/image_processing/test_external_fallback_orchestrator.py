"""Contract tests for ExternalProviderFallbackOrchestrator with a fake provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisContext,
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
    ExternalImageInput,
)
from src.application.services.image_processing.external_provider_fallback_orchestrator import (
    ExternalFallbackSnapshot,
    ExternalProviderFallbackOrchestrator,
    FallbackProgressCounters,
)
from src.application.services.image_processing.external_result_normalizer import (
    ExternalResultNormalizer,
)
from src.application.services.image_processing.fallback_eligibility_policy import (
    FallbackEligibilityPolicy,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)
from src.domain.jobs.entities import Job, JobStatus


class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeAttemptRepo:
    def __init__(self) -> None:
        self.rows: list[ProcessingAttempt] = []

    def save(self, attempt: ProcessingAttempt) -> None:
        for i, row in enumerate(self.rows):
            if row.id == attempt.id:
                self.rows[i] = attempt
                return
        self.rows.append(attempt)

    def get_by_id(self, attempt_id: str) -> ProcessingAttempt | None:
        return next((r for r in self.rows if r.id == attempt_id), None)

    def get_by_unique_key(self, job_id, asset_id, strategy, attempt_number):
        return next(
            (
                r
                for r in self.rows
                if r.job_id == job_id
                and r.asset_id == asset_id
                and r.strategy == strategy
                and r.attempt_number == attempt_number
            ),
            None,
        )

    def list_by_job_and_asset(self, job_id, asset_id):
        return [r for r in self.rows if r.job_id == job_id and r.asset_id == asset_id]

    def list_by_job(self, job_id):
        return [r for r in self.rows if r.job_id == job_id]

    def next_attempt_number(self, job_id, asset_id, strategy) -> int:
        nums = [
            r.attempt_number
            for r in self.rows
            if r.job_id == job_id and r.asset_id == asset_id and r.strategy == strategy
        ]
        return (max(nums) if nums else 0) + 1

    def create_next_attempt(self, **kwargs) -> ProcessingAttempt:
        number = self.next_attempt_number(
            kwargs["job_id"], kwargs["asset_id"], kwargs["strategy"]
        )
        attempt = ProcessingAttempt(
            id=str(uuid4()),
            job_id=kwargs["job_id"],
            asset_id=kwargs["asset_id"],
            strategy=kwargs["strategy"],
            attempt_number=number,
            status=kwargs["status"],
            created_at=kwargs["now"],
            provider=kwargs.get("provider"),
            model=kwargs.get("model"),
            started_at=kwargs["now"],
            execution_scope=kwargs.get("execution_scope"),
            configuration_snapshot_version=kwargs.get("configuration_snapshot_version"),
            worker_token=kwargs.get("worker_token"),
            logical_asset_attempt=kwargs.get("logical_asset_attempt", True),
        )
        self.save(attempt)
        return attempt

    def list_started_by_job(self, job_id):
        return [
            r
            for r in self.rows
            if r.job_id == job_id and r.status is ProcessingAttemptStatus.STARTED
        ]


@dataclass
class _FakeProvider:
    calls: list[str] = field(default_factory=list)
    result: ExternalAnalysisResult | None = None

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-model"

    def analyze_image(
        self, image: ExternalImageInput, context: ExternalAnalysisContext
    ) -> ExternalAnalysisResult:
        self.calls.append(context.asset_id)
        assert self.result is not None
        return self.result


def _job() -> Job:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        identification_mode_source=AisleIdentificationModeSource.REQUEST,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        configuration_snapshot_version=1,
        engine_params_json={},
    )


def _asset() -> SourceAsset:
    return SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="asset-1.jpg",
        storage_path="/asset-1.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _internal_unrecognized() -> ImageProcessingResult:
    return ImageProcessingResult(
        job_id="job-1",
        asset_id="asset-1",
        status=ImageResultStatus.UNRECOGNIZED,
        processing_mode="CODE_SCAN",
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
    )


def _snapshot(*, enabled: bool = True) -> ExternalFallbackSnapshot:
    return ExternalFallbackSnapshot(
        enabled=enabled,
        provider="fake",
        model="fake-model",
        prompt_key="k",
        prompt_version="1",
        timeout_seconds=30,
        max_attempts=1,
        max_concurrency=1,
        max_image_dimension=1024,
        quantity_max=999,
        circuit_breaker_threshold=5,
        circuit_breaker_cooldown_seconds=60,
    )


def test_resolved_internal_skips_provider() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(status=ExternalAnalysisStatus.VALID)
    )
    orch = ExternalProviderFallbackOrchestrator(
        provider=provider,
        content_reader=lambda _a: b"img",
        attempt_repo=_FakeAttemptRepo(),
        clock=_FakeClock(),
        eligibility=FallbackEligibilityPolicy(enabled=True),
        normalizer=ExternalResultNormalizer(),
        counters=FallbackProgressCounters(),
    )
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=ImageProcessingResult(
            job_id="job-1",
            asset_id="asset-1",
            status=ImageResultStatus.RESOLVED_INTERNAL,
            processing_mode="CODE_SCAN",
            internal_code="X",
            quantity=1,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        ),
        worker_token="w",
        snapshot=_snapshot(),
    )
    assert out is None
    assert provider.calls == []


def test_unrecognized_calls_provider_and_resolves() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.VALID,
            internal_code="CODE1",
            quantity=2,
            provider_name="fake",
            model_name="fake-model",
        )
    )
    repo = _FakeAttemptRepo()
    orch = ExternalProviderFallbackOrchestrator(
        provider=provider,
        content_reader=lambda _a: b"img",
        attempt_repo=repo,
        clock=_FakeClock(),
        eligibility=FallbackEligibilityPolicy(enabled=True),
        normalizer=ExternalResultNormalizer(),
        counters=FallbackProgressCounters(),
    )
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(),
    )
    assert out is not None
    assert out.status is ImageResultStatus.RESOLVED_EXTERNAL
    assert provider.calls == ["asset-1"]
    assert any(a.strategy == "EXTERNAL_PROVIDER" for a in repo.rows)


def test_snapshot_disabled_skips() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(status=ExternalAnalysisStatus.VALID)
    )
    orch = ExternalProviderFallbackOrchestrator(
        provider=provider,
        content_reader=lambda _a: b"img",
        attempt_repo=_FakeAttemptRepo(),
        clock=_FakeClock(),
        eligibility=FallbackEligibilityPolicy(enabled=True),
        normalizer=ExternalResultNormalizer(),
    )
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(enabled=False),
    )
    assert out is None
    assert provider.calls == []
