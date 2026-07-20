"""Contract tests for ExternalProviderFallbackOrchestrator (Phase 5 corrections)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisContext,
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
    ExternalImageInput,
)
from src.application.services.image_processing.external_circuit_breaker import (
    CircuitState,
    ExternalCircuitBreaker,
)
from src.application.services.image_processing.external_provider_fallback_orchestrator import (
    ExternalFallbackSnapshot,
    ExternalProviderFallbackOrchestrator,
    FallbackProgressCounters,
    aggregate_fallback_progress_from_requests,
)
from src.application.services.image_processing.external_result_normalizer import (
    ExternalResultNormalizer,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.external_image_analysis_request import (
    ExternalRequestStatus,
)
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_external_image_analysis_request_repository import (
    MemoryExternalImageAnalysisRequestRepository,
)


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
    results: list[ExternalAnalysisResult] = field(default_factory=list)
    _idx: int = 0

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
        if self.results:
            out = self.results[min(self._idx, len(self.results) - 1)]
            self._idx += 1
            return out
        assert self.result is not None
        return self.result


class _Factory:
    def __init__(self, provider: _FakeProvider) -> None:
        self._provider = provider

    def resolve(self, *, provider: str, model: str | None):
        return self._provider


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
        error_code="NO_CODE",
    )


def _snapshot(*, enabled: bool = True, max_attempts: int = 1) -> ExternalFallbackSnapshot:
    return ExternalFallbackSnapshot(
        enabled=enabled,
        provider="fake",
        model="fake-model",
        prompt_key="k",
        prompt_version="1",
        timeout_seconds=30,
        max_attempts=max_attempts,
        max_concurrency=1,
        max_image_dimension=1024,
        quantity_max=999,
        circuit_breaker_threshold=5,
        circuit_breaker_cooldown_seconds=60,
        recoverable_technical_codes=("NO_CODE", "DECODE_FAILED"),
        retry_backoff_seconds=0.01,
        client_rules={
            "prefer_ean_as_internal_code": True,
            "required_fields": ["internal_code", "quantity"],
            "client_rule_key": "ean_first",
        },
    )


def _orch(
    provider: _FakeProvider,
    *,
    attempt_repo: _FakeAttemptRepo | None = None,
    request_repo: MemoryExternalImageAnalysisRequestRepository | None = None,
    is_cancelled=None,
    circuit_breaker=None,
) -> tuple[ExternalProviderFallbackOrchestrator, _FakeAttemptRepo, MemoryExternalImageAnalysisRequestRepository]:
    attempts = attempt_repo or _FakeAttemptRepo()
    requests = request_repo or MemoryExternalImageAnalysisRequestRepository()
    orch = ExternalProviderFallbackOrchestrator(
        content_reader=lambda _a: b"img",
        attempt_repo=attempts,
        request_repo=requests,
        clock=_FakeClock(),
        provider_factory=_Factory(provider),
        provider=provider,
        normalizer=ExternalResultNormalizer(),
        counters=FallbackProgressCounters(),
        is_cancelled=is_cancelled,
        circuit_breaker=circuit_breaker,
    )
    return orch, attempts, requests


def test_resolved_internal_skips_provider() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(status=ExternalAnalysisStatus.VALID)
    )
    orch, _, _ = _orch(provider)
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
        client_id="client-1",
    )
    assert out.skipped is True
    assert provider.calls == []


def test_unrecognized_calls_provider_leaves_attempt_started_until_finalize() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.VALID,
            internal_code="CODE1",
            quantity=2,
            provider_name="fake",
            model_name="fake-model",
            raw_reference="resp-hash-abc",
            additional_fields={"request_image_sha256": "img-hash-xyz"},
        )
    )
    orch, repo, req_repo = _orch(provider)
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(),
        client_id="client-1",
    )
    assert out.skipped is False
    assert out.result is not None
    assert out.result.status is ImageResultStatus.RESOLVED_EXTERNAL
    assert out.persistence_status == "PENDING"
    assert provider.calls == ["asset-1"]
    assert out.attempt is not None
    assert out.attempt.status is ProcessingAttemptStatus.STARTED
    assert out.request is not None
    assert out.request.status is ExternalRequestStatus.PERSISTENCE_PENDING
    assert out.request.provider_response_sha256 == "resp-hash-abc"
    assert out.request.request_image_sha256 == "img-hash-xyz"

    orch.finalize_after_persist(
        attempt=out.attempt,
        request=out.request,
        result=out.result,
        position_id="pos-1",
        active_result_id="ar-1",
        persisted=True,
    )
    saved = repo.get_by_id(out.attempt.id)
    assert saved is not None
    assert saved.status is ProcessingAttemptStatus.SUCCEEDED
    refreshed = req_repo.get_by_id(out.request.id)
    assert refreshed is not None
    assert refreshed.status is ExternalRequestStatus.PERSISTED


def test_provider_valid_persistence_failed_keeps_attempt_failed() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.VALID,
            internal_code="CODE1",
            quantity=2,
            provider_name="fake",
            model_name="fake-model",
        )
    )
    orch, repo, _ = _orch(provider)
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(),
        client_id="c1",
    )
    assert out.attempt is not None and out.result is not None
    failed = ImageProcessingResult(
        job_id="job-1",
        asset_id="asset-1",
        status=ImageResultStatus.FAILED_TECHNICAL,
        processing_mode="EXTERNAL_PROVIDER",
        error_code="PROCESSING_PERSISTENCE_FAILED",
        error_message="persist boom",
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
        normalized_result=out.result.normalized_result,
    )
    orch.finalize_after_persist(
        attempt=out.attempt,
        request=out.request,
        result=failed,
        position_id=None,
        active_result_id=None,
        persisted=False,
    )
    saved = repo.get_by_id(out.attempt.id)
    assert saved is not None
    assert saved.status is ProcessingAttemptStatus.FAILED_TECHNICAL
    assert (saved.extra or {}).get("persistence_status") == "FAILED"
    assert (saved.extra or {}).get("provider_call_status") == "SUCCEEDED"


def test_reuse_normalized_skips_second_provider_call() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.VALID,
            internal_code="CODE1",
            quantity=2,
            provider_name="fake",
            model_name="fake-model",
        )
    )
    orch, _, req_repo = _orch(provider)
    first = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(),
        client_id="c1",
    )
    assert first.request is not None
    assert len(provider.calls) == 1
    # Simulate crash after durable normalized response.
    first.request.status = ExternalRequestStatus.PROVIDER_SUCCEEDED
    req_repo.save(first.request)

    second = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w2",
        snapshot=_snapshot(),
        client_id="c1",
    )
    assert len(provider.calls) == 1
    assert second.result is not None
    assert second.result.additional_fields.get("reused_normalized_response") is True


def test_snapshot_disabled_skips() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(status=ExternalAnalysisStatus.VALID)
    )
    orch, _, _ = _orch(provider)
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(enabled=False),
    )
    assert out.skipped is True
    assert provider.calls == []


def test_max_attempts_retries_timeout() -> None:
    provider = _FakeProvider(
        results=[
            ExternalAnalysisResult(
                status=ExternalAnalysisStatus.TIMEOUT,
                provider_name="fake",
                model_name="fake-model",
            ),
            ExternalAnalysisResult(
                status=ExternalAnalysisStatus.VALID,
                internal_code="R2",
                quantity=1,
                provider_name="fake",
                model_name="fake-model",
            ),
        ]
    )
    orch, _, _ = _orch(provider)
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(max_attempts=2),
        client_id="c1",
    )
    assert len(provider.calls) == 2
    assert out.result is not None
    assert out.result.status is ImageResultStatus.RESOLVED_EXTERNAL


def test_non_retryable_invalid_does_not_retry() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.INVALID,
            provider_name="fake",
            model_name="fake-model",
        )
    )
    orch, _, _ = _orch(provider)
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(max_attempts=3),
    )
    assert len(provider.calls) == 1
    assert out.result is not None
    assert out.result.status is ImageResultStatus.UNRECOGNIZED


def test_cancellation_marks_cancelled_not_technical_failure() -> None:
    provider = _FakeProvider(
        result=ExternalAnalysisResult(status=ExternalAnalysisStatus.VALID)
    )
    cancelled = {"v": False}

    def _is_cancelled() -> bool:
        return cancelled["v"]

    orch, repo, _ = _orch(provider, is_cancelled=_is_cancelled)
    cancelled["v"] = True
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(),
    )
    assert out.cancelled is True
    assert provider.calls == []
    assert orch.counters is not None
    assert orch.counters.external_failed == 0


def test_circuit_breaker_half_open_single_probe_concurrent() -> None:
    import threading
    import time

    cb = ExternalCircuitBreaker(failure_threshold=1, cooldown_seconds=1.0)
    cb.record_failure("fake", "m")
    assert cb.state_of("fake", "m") is CircuitState.OPEN
    time.sleep(1.05)
    acquired: list[bool] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        acquired.append(cb.try_acquire_call("fake", "m"))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for x in acquired if x) == 1
    assert sum(1 for x in acquired if not x) == 7
    cb.record_success("fake", "m")
    assert cb.state_of("fake", "m") is CircuitState.CLOSED


def test_client_rules_prefer_ean() -> None:
    n = ExternalResultNormalizer()
    result = n.normalize(
        job_id="j1",
        asset_id="a1",
        analysis=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.VALID,
            internal_code="ART-9",
            quantity=3,
            normalized_result={"ean": "7791234567890", "internal_code": "ART-9"},
        ),
        client_rules={"prefer_ean_as_internal_code": True},
        client_id="masol-like",
    )
    assert result.status is ImageResultStatus.RESOLVED_EXTERNAL
    assert result.internal_code == "7791234567890"
    assert result.additional_fields.get("client_id") == "masol-like"


def test_aggregate_progress_from_requests() -> None:
    orch, _, req_repo = _orch(
        _FakeProvider(
            result=ExternalAnalysisResult(
                status=ExternalAnalysisStatus.VALID,
                internal_code="C",
                quantity=1,
                provider_name="fake",
                model_name="fake-model",
                estimated_cost=0.01,
            )
        )
    )
    out = orch.process_if_eligible(
        job=_job(),
        asset=_asset(),
        internal_result=_internal_unrecognized(),
        worker_token="w",
        snapshot=_snapshot(),
    )
    assert out.request is not None
    orch.finalize_after_persist(
        attempt=out.attempt,  # type: ignore[arg-type]
        request=out.request,
        result=out.result,  # type: ignore[arg-type]
        position_id="p1",
        active_result_id="a1",
        persisted=True,
    )
    rows = list(req_repo.list_by_job("job-1"))
    progress = aggregate_fallback_progress_from_requests(rows, resolved_internal=2)
    assert progress["resolved_external"] == 1
    assert progress["resolved_internal"] == 2
